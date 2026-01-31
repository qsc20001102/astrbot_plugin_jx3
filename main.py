# pyright: reportOptionalMemberAccess=false

import json
import shutil
import pathlib
import asyncio
import inspect
from pathlib import Path
from typing import Union

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api import AstrBotConfig
import astrbot.api.message_components as Comp

from .core.jx3_data import JX3Service
from .core.async_task import AsyncTask
from .core.jx3_commands import JX3Commands

@register("astrbot_plugin_jx3", 
          "fxdyz", 
          "通过接口调用剑网三API接口获取游戏数据，整理发送。", 
          "1.0.0",
          "https://github.com/qsc20001102/astrbot_plugin_jx3api.git"
)
class Jx3ApiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        #获取配置
        self.conf = config

        # 本地数据存储路径
        self.local_data_dir = StarTools.get_data_dir("astrbot_plugin_jx3")

        # 插件数据文件路径
        self.data_file_path = Path(__file__).parent / "data"

        # 读取API配置文件
        self.api_file_path = Path(__file__).parent / "data" / "api_config.json"
        with open(self.api_file_path, 'r', encoding='utf-8') as f:
            self.api_config = json.load(f) 

        # 初始化数据
        # 指令前缀
        self.prefix_en = self.conf.get("prefix").get("enable")
        self.prefix_text = self.conf.get("prefix").get("text")
        if not self.prefix_text:
            self.prefix_text = "剑三"
        if self.prefix_en:
            logger.info(f"已启用指令前缀功能，前缀为：{self.prefix_text}")
        else:
            logger.info(f"未启用指令前缀功能。")
        # 默认服务器
        self.server = self.conf.get("server", "梦江南")
        # 声明指令集
        self.command_map = {}
        logger.info(f"配置加载默认服务器：{self.server}")

        logger.info(f"指令集初始完成。")
        logger.info("jx3api插件初始化完成")


    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""     
        # --- 调用函数完成检查和复制 ---
        try:
            loop = asyncio.get_running_loop()
            self.file_local_data = await loop.run_in_executor(
                None,
                self.check_and_copy_db,
                self.local_data_dir,
                "local_async.json",
                self.data_file_path
            )
        except FileNotFoundError as e:
            logger.critical(f"插件初始化失败：{e}")
            raise

        try:
            self.jx3fun = JX3Service(self.api_config, self.conf)
            self.at = AsyncTask(self.context, self.conf, self.jx3fun)
            await self.at.init_tasks()
            self.jx3com = JX3Commands(self.jx3fun,self.at,self.server)
        except Exception as e:
            if hasattr(self, "at"):
                await self.at.destroy()  
            logger.error(f"功能模块初始化失败: {e}")
            raise

        # 指令集
        self.ini_command_map()

        logger.info("jx3api 异步插件初始化完成")


    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        if self.at:
            await self.at.destroy()
            self.at = None

        if self.jx3fun:
            await self.jx3fun.close()
            self.jx3fun = None
        logger.info("jx3api插件已卸载/停用")


    def check_and_copy_db(self, local_data_dir: Union[str, Path], db_filename: str, default_db_dir: Union[str, Path]) -> pathlib.Path:
        """
        检查本地数据目录中是否存在指定的数据库文件。
        如果不存在，则从默认目录复制该文件。
        """
        # 目标路径
        target_dir = pathlib.Path(local_data_dir)
        target_file_path = target_dir / db_filename
        # 源文件路径
        source_file_path = pathlib.Path(default_db_dir) / db_filename
        # 假设默认文件名为 local_data.db
        if not target_file_path.exists():
            logger.warning(f"本地数据库文件 {target_file_path.name} 不存在，正在从默认位置复制...")
            # 1. 确保目标文件夹存在
            target_dir.mkdir(parents=True, exist_ok=True)
            # 2. 检查源文件是否存在
            if not source_file_path.exists():
                raise FileNotFoundError(f"默认数据库源文件未找到！请检查路径: {source_file_path}")
            # 3. 复制文件
            shutil.copy(source_file_path, target_file_path)
            logger.info(f"数据库文件已成功复制到: {target_file_path}")
        else:
            logger.info(f"本地数据库文件 {target_file_path} 已存在，跳过复制。")
        return target_file_path

    
    def serverdefault(self,server):
        """加载配置默认服务器"""
        if server == "":
            return self.server
        return server


    def parse_message(self, text: str) -> list[str] | None:
        """消息解析"""
        text = text.strip()
        if not text:
            return None

        # 前缀模式
        if self.prefix_en:
            prefix = self.prefix_text
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
            else:
                # 非前缀消息，直接忽略
                return None

        return text.split()


    async def _call_with_auto_args(self, handler, event: AstrMessageEvent, args: list[str]):
        """指令执行函数"""
        sig = inspect.signature(handler)
        params = list(sig.parameters.values())

        call_args = []
        arg_index = 0

        for p in params:
            if p.name == "self":
                continue

            if p.name == "event":
                call_args.append(event)
                continue

            if arg_index < len(args):
                raw = args[arg_index]
                arg_index += 1
                try:
                    if p.annotation is int:
                        call_args.append(int(raw))
                    elif p.annotation is float:
                        call_args.append(float(raw))
                    else:
                        call_args.append(raw)
                except Exception:
                    call_args.append(p.default)
            else:
                if p.default is not inspect._empty:
                    call_args.append(p.default)
                else:
                    raise ValueError(f"缺少参数: {p.name}")

        # 只允许 coroutine
        return await handler(*call_args)


    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        """解析所有消息"""
        if not self.command_map:
            logger.debug("插件尚未初始化完成，忽略消息")
            return
        parts = self.parse_message(event.message_str)
        if not parts:
            logger.debug("未触发指令，忽略消息")
            return

        cmd, *args = parts
        handler = self.command_map.get(cmd)
        if not handler:
            logger.debug("指令函数为空，忽略消息")
            return

        try:
            event.stop_event()
            ret = await self._call_with_auto_args(handler, event, args)
            if ret is not None:
                yield ret
        except Exception as e:
            logger.exception(f"指令执行失败: {cmd}, error={e}")
            yield event.plain_result("参数错误或执行失败")


    def ini_command_map(self):
        """初始化指令集"""
        self.command_map = {
            "功能": self.jx3com.jx3_helps,
            "日常": self.jx3com.jx3_richang,
            "日常预测": self.jx3com.jx3_richangyuche,
            "名望": self.jx3com.jx3_xingxiashijian,
            "开服": self.jx3com.jx3_kaifu,
            "全服状态": self.jx3com.jx3_zhuangtai,
            "骚话": self.jx3com.jx3_shaohua,
            "技改": self.jx3com.jx3_jigai,
            "公告": self.jx3com.jx3_xinwen,
            "科举": self.jx3com.jx3_keju,
            "花价": self.jx3com.jx3_huajia,
            "装饰": self.jx3com.jx3_zhuangshi,
            "器物": self.jx3com.jx3_qiwu,
            "沙盘": self.jx3com.jx3_shapan,
            "奇遇统计": self.jx3com.jx3_qufuqiyu,
            "奇遇攻略": self.jx3com.jx3_qiyugonglue,
            "宏": self.jx3com.jx3_hong,
            "配装": self.jx3com.jx3_peizhuang,
            "金价": self.jx3com.jx3_jinjia,
            "物价": self.jx3com.jx3_wujia,
            "交易行": self.jx3com.jx3_jiaoyihang,
            "名片": self.jx3com.jx3_jueshemingpian,
            "随机名片": self.jx3com.jx3_shuijimingpian,
            "烟花": self.jx3com.jx3_yanhuachaxun,
            "的卢": self.jx3com.jx3_dilujilu,
            "招募": self.jx3com.jx3_tuanduizhaomu,
            "战绩": self.jx3com.jx3_zhanji,
            "奇遇": self.jx3com.jx3_qiyu,
            "阵营拍卖": self.jx3com.jx3_zhengyingpaimai,
            "扶摇九天": self.jx3com.jx3_fuyaojjiutian,
            "刷马": self.jx3com.jx3_shuma,
            "骗子": self.jx3com.jx3_pianzhi,
            "八卦": self.jx3com.jx3_bagua,
            "开服监控": self.jx3com.jx3_kaifhujiank,
            "新闻推送": self.jx3com.jx3_xinwenzhixun,
            "刷马推送": self.jx3com.jx3_shuamamsg,
            "赤兔推送": self.jx3com.jx3_chitusg,
        }






