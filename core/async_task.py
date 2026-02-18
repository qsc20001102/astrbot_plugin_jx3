# pyright: reportArgumentType=false
import asyncio
import json
import aiofiles

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api import AstrBotConfig


from .jx3_data import JX3Service
from .sqlite import AsyncSQLiteDB

class AsyncTask:
    """
    基于 APScheduler 的后台异步监控任务管理类
    """

    def __init__(self, context: Context, config: AstrBotConfig, jx3api: JX3Service, sqlite: AsyncSQLiteDB):
        self.context = context
        self.conf = config
        self.jx3fun = jx3api
        self.sql = sqlite

        self.server = self.conf.get("server", "梦江南")
        
        self.scheduler = AsyncIOScheduler()
        self.tasks = {}  
        
        logger.info(f"初始化推送功能成功")

    
    """===================== 本地读写 ====================="""

    async def set_local_data(self, key: str, value):
        try:
            allowed = {"kfts", "xwts", "smts", "ctts"}
            if key not in allowed:
                raise ValueError("非法字段")
            
            await self.sql.update(
                "tuishong",
                {
                    key: value,
                },
                "id=?",
                (1,)
            )
        except Exception as e:
            logger.error(f"数据写入失败：{e}")


    async def get_local_data(self, key: str, default: int=0):
        try:
            allowed = {"kfts", "xwts", "smts", "ctts"}
            if key not in allowed:
                return default
            
            data = await self.sql.select_one(
                    "tuishong",
                    "id=?",
                    (1,)
                )   
            if data:                    
                return data.get(key, default)
            else:
                return default
        except Exception as e:
            logger.error(f"数据读取失败：{e}")


    """===================== 通用后台任务 ====================="""

    async def _job_common(self, fetch_func, task_key: str, namefun: str):
        state = self.tasks[task_key]

        try:
            data = await fetch_func()

            if not isinstance(data, dict):
                raise ValueError("fetch_func 返回数据不是 dict")

            state["state_new"] = data.get("status")

            if state["state_old"] != state["state_new"]:
                message_chain = MessageChain().message(data.get("data"))

                for umo in state["umos"]:
                    await self.context.send_message(umo, message_chain)

                await self.set_local_data(task_key, state["state_new"])
                state["state_old"] = state["state_new"]

        except asyncio.CancelledError:
            # 调度器 shutdown 时的正常路径
            raise

        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"{namefun} 数据结构异常: {e}")

        except Exception as e:
            logger.exception(f"{namefun} 后台任务执行异常")

    """===================== 初始化任务 ====================="""

    async def init_tasks(self):
        settings = [
            ("kfts", "开服监控", lambda: self.jx3fun.kaifu(self.server)),
            ("xwts", "新闻资讯", lambda: self.jx3fun.xinwen(1)),
            ("smts", "刷马消息", lambda: self.jx3fun.shuamamsg(self.server,type="horse",subtype="foreshow")),
            ("ctts", "赤兔消息", lambda: self.jx3fun.shuamamsg(self.server,type="chitu-horse",subtype="share_msg")),
        ]

        for key, name, fetch in settings:
            conf = self.conf.get(key, {})

            state_old = await self.get_local_data(key, default=False)
            self.tasks[key] = {
                "enable": conf.get("enable", True),
                "interval": conf.get("time", 60),
                "umos": conf.get("umos", []),
                "state_old": state_old,
                "state_new": state_old
            }

            if self.tasks[key]["enable"]:
                if self.tasks[key]["umos"]:
                    self._add_scheduler(key, name, fetch)
                else:
                    logger.warning(f"{name} 推送对象为空，任务未启动")

        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("后台监控调度器已启动")

    """===================== 调度操作 ====================="""

    def _add_scheduler(self, key, namefun, fetch_func):
        if self.scheduler.get_job(key):
            self.scheduler.remove_job(key)

        interval = self.tasks[key]["interval"]
        self.scheduler.add_job(
            func=self._job_common,
            trigger=IntervalTrigger(seconds=interval),
            id=key,
            args=[fetch_func, key, namefun]
        )

        logger.info(f"{namefun}后台任务启动成功，周期：{interval}s")

    def stop_all_tasks(self):
        """
        停止并移除所有任务
        """
        try:
            self.scheduler.remove_all_jobs()
            for key in self.tasks:
                self.tasks[key]["enable"] = False
            logger.info("已停止全部后台任务")
        except Exception as e:
            logger.error(f"停止全部后台任务失败：{e}")

    async def destroy(self):
        try:
            self.stop_all_tasks()
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
            self.tasks.clear()
            logger.info("后台调度器已销毁")
        except Exception as e:
            logger.error(f"销毁调度器失败：{e}")

    async def get_task_info(self, key: str) -> str:
        try:
            t = self.tasks[key]
            return (
                f"功能：{key}\n"
                f"启用：{t['enable']}\n"
                f"周期：{t['interval']} 秒\n"
                f"旧状态：{t['state_old']}\n"
                f"推送对象：{t['umos']}"
            )
        except Exception as e:
            return f"读取后台配置失败：{e}"
