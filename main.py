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
from astrbot.core.utils.session_waiter import (
    SessionController,
    session_waiter,
)

from .core.sqlite import AsyncSQLiteDB
from .core.jx3_data import JX3Service
from .core.async_task import AsyncTask
from .core.bilei_data import BiLeidata

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

        # SQLite本地路径
        self.sqlite_path = Path(self.local_data_dir) /"sqlite.db"
        logger.info(f"SQLite数据文件路径：{self.sqlite_path}")

        # 插件自带数据文件路径
        self.data_file_path = Path(__file__).parent / "data"

        # 读取API配置文件
        self.api_file_path = Path(__file__).parent / "data" / "api_config.json"
        with open(self.api_file_path, 'r', encoding='utf-8') as f:
            self.api_config = json.load(f) 


        # 初始化数据
        # 指令前缀功能
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
        logger.info(f"配置加载默认服务器：{self.server}")

        # 声明指令集
        self.command_map = {}

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
            # sqlite 实例化
            self.sql_db = AsyncSQLiteDB(self.sqlite_path) # pyright: ignore[reportArgumentType]
            await self.sql_db.connect()
            await self.sql_db.execute("""
            CREATE TABLE IF NOT EXISTS bilei(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                text TEXT,
                time TEXT,
                user TEXT                                           
            )
            """)

            # 避雷功能 实例化
            self.bilei = BiLeidata(self.sql_db)

            # 剑三功能 实例化
            self.jx3fun = JX3Service(self.api_config, self.conf)
            
            # 后台推送 实例化
            self.at = AsyncTask(self.context, self.conf, self.jx3fun)
            await self.at.init_tasks()

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

        if self.sql_db:
            await self.sql_db.close()
            self.sql_db = None
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
            "功能": self.jx3_helps,
            "日常": self.jx3_richang,
            "日常预测": self.jx3_richangyuche,
            "名望": self.jx3_xingxiashijian,
            "开服": self.jx3_kaifu,
            "全服状态": self.jx3_zhuangtai,
            "骚话": self.jx3_shaohua,
            "技改": self.jx3_jigai,
            "公告": self.jx3_xinwen,
            "科举": self.jx3_keju,
            "花价": self.jx3_huajia,
            "装饰": self.jx3_zhuangshi,
            "器物": self.jx3_qiwu,
            "沙盘": self.jx3_shapan,
            "奇遇统计": self.jx3_qufuqiyu,
            "奇遇攻略": self.jx3_qiyugonglue,
            "宏": self.jx3_hong,
            "配装": self.jx3_peizhuang,
            "金价": self.jx3_jinjia,
            "物价": self.jx3_wujia,
            "交易行": self.jx3_jiaoyihang,
            "名片": self.jx3_jueshemingpian,
            "随机名片": self.jx3_shuijimingpian,
            "烟花": self.jx3_yanhuachaxun,
            "的卢": self.jx3_dilujilu,
            "招募": self.jx3_tuanduizhaomu,
            "战绩": self.jx3_zhanji,
            "奇遇": self.jx3_qiyu,
            "阵营拍卖": self.jx3_zhengyingpaimai,
            "扶摇九天": self.jx3_fuyaojjiutian,
            "刷马": self.jx3_shuma,
            "骗子": self.jx3_pianzhi,
            "八卦": self.jx3_bagua,
            "避雷添加": self.bilei_add,
            "避雷查看": self.bilei_all,
            "避雷查询": self.bilei_select,
            "避雷修改": self.bilei_update,
            "避雷删除": self.bilei_delete,
            "开服监控": self.jx3_kaifhujiank,
            "新闻推送": self.jx3_xinwenzhixun,
            "刷马推送": self.jx3_shuamamsg,
            "赤兔推送": self.jx3_chitusg,
        }


    def serverdefault(self,server):
        """加载配置默认服务器"""
        if server == "":
            return self.server
        return server


    async def plain_msg(self, event: AstrMessageEvent, action):
        """最终将数据整理成文本发送"""
        data= await action()
        try:
            if data["code"] == 200:
                await event.send( event.plain_result(data["data"]))
            else:
                await event.send(event.plain_result(data["msg"])) 
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试")) 


    async def T2I_image_msg(self, event: AstrMessageEvent, action):
        """最终将数据渲染成图片发送"""
        data = await action()
        try:
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                await event.send(event.image_result(url)) 
            else:
                await event.send(event.plain_result(data["msg"])) 

        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试")) 


    async def image_msg(self, event: AstrMessageEvent, action):
        """最终将数据整理成图片发送"""
        data = await action()
        try:
            if data["code"] == 200:
                await event.send(event.image_result(data["data"])) 
            else:
                await event.send(event.plain_result(data["msg"])) 

        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试")) 



    async def jx3_helps(self, event: AstrMessageEvent):
        """剑三 功能"""
        return await self.T2I_image_msg(event, self.jx3fun.helps)


    async def jx3_richang(self, event: AstrMessageEvent,server: str = "" ,num: int = 0):
        """剑三 日常 服务器 天数"""
        return await self.plain_msg(event, lambda: self.jx3fun.richang(self.serverdefault(server),num))


    async def jx3_richangyuche(self, event: AstrMessageEvent):
        """剑三 日常预测"""
        return await self.T2I_image_msg(event, self.jx3fun.richangyuche)


    async def jx3_xingxiashijian(self, event: AstrMessageEvent,name: str = "穹野卫"):
        """剑三 名望"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.xingxiashijian(name))


    async def jx3_kaifu(self, event: AstrMessageEvent,server: str = ""):
        """剑三 开服 服务器"""
        return await self.plain_msg(event, lambda: self.jx3fun.kaifu(self.serverdefault(server)))


    async def jx3_zhuangtai(self, event: AstrMessageEvent):
        """剑三 状态"""
        return await self.T2I_image_msg(event, self.jx3fun.zhuangtai)

     
    async def jx3_shaohua(self, event: AstrMessageEvent,):
        """剑三 骚话"""
        return await self.plain_msg(event, self.jx3fun.shaohua)


    async def jx3_jigai(self, event: AstrMessageEvent,):
        """剑三 技改"""
        return await self.plain_msg(event, self.jx3fun.jigai)


    async def jx3_xinwen(self, event: AstrMessageEvent,num:int = 5):
        """剑三 新闻"""
        return await self.plain_msg(event, lambda: self.jx3fun.xinwen(num))
 

    async def jx3_keju(self, event: AstrMessageEvent,subject: str, limit: int = 5):
        """剑三 科举"""
        return await self.plain_msg(event, lambda: self.jx3fun.keju(subject,limit))


    async def jx3_huajia(self, event: AstrMessageEvent,  name: str= "", server: str = "", map: str= ""):
        """剑三 花价 名称 服务器 地图"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.huajia(self.serverdefault(server),name,map))


    async def jx3_zhuangshi(self, event: AstrMessageEvent,  name: str):
        """剑三 装饰 名称"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.zhuangshi(name))


    async def jx3_qiwu(self, event: AstrMessageEvent,  name: str):
        """剑三 器物 地图名称"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.qiwu(name))
            

    async def jx3_shapan(self, event: AstrMessageEvent,server: str = ""):
        """剑三 沙盘 服务器"""
        return await self.image_msg(event, lambda: self.jx3fun.shapan(self.serverdefault(server)))  


    async def jx3_qufuqiyu(self, event: AstrMessageEvent,adventureName: str = "阴阳两界", server: str = ""):
        """剑三 奇遇统计 奇遇名称 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.qiyu(adventureName,self.serverdefault(server)))
 

    async def jx3_qiyugonglue(self, event: AstrMessageEvent,name: str):
        """剑三 奇遇攻略 奇遇名称"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.qiyugonglue(name))


    async def jx3_hong(self, event: AstrMessageEvent, kungfu: str = "易筋经"):
        """剑三 宏 心法"""
        # 获取宏列表
        try:
            data = await self.jx3fun.hong1(kungfu)
            if data["code"] == 200:
                await event.send(event.plain_result(data["msg"])) 
                # 获取用户ID
                user_id = event.get_sender_id()
                # 等等用户回复
                @session_waiter(timeout=30)
                async def macro_select_waiter(controller: SessionController,new_event: AstrMessageEvent):
                    if new_event.get_sender_id() != user_id:
                        return

                    msg = new_event.get_message_str().strip()

                    if not msg.isdigit():
                        await new_event.send(
                            MessageChain().message("输入异常，结束会话")
                        )
                        controller.stop()
                        return

                    num = int(msg)
                    if num < 1 or num > data["data"]["num"]:
                        await new_event.send(
                            MessageChain().message("无效序号，结束会话")
                        )
                        controller.stop()
                        return

                    try:
                        data1 = await self.jx3fun.hong2(data["data"]["pid"][num])
                        if data1["code"] != 200:
                            await new_event.send(
                                MessageChain().message("获取详细宏数据失败")
                            )
                            controller.stop()
                            return
                        
                        chain = MessageChain()
                        if data1["temp"] != "":
                            url = await self.html_render(data1["temp"], {}, options={})
                            chain.url_image(url)

                        msg_text = data1["data"]
                        chain.message(msg_text)
                        await new_event.send(chain)

                    except Exception as e:
                        logger.error(f"功能函数执行错误: {e}")
                        await new_event.send(
                            MessageChain().message("猪脑过载，请稍后再试")
                        )

                    controller.stop()

                try:
                    await macro_select_waiter(event)  
                except TimeoutError:
                    await event.send(event.plain_result("选择宏超时，已结束会话")) 
                except Exception:
                    logger.error("宏选择发生异常", exc_info=True)
            else:
                await event.send(event.plain_result(f"未搜索到与【{kungfu}】相关的宏")) 
                return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试"))


    async def jx3_peizhuang(self, event: AstrMessageEvent,name: str = "易筋经", tags: str = ""):
        """剑三 配装 心法"""
        return await self.plain_msg(event, lambda: self.jx3fun.peizhuang( name,tags))


    async def jx3_jinjia(self, event: AstrMessageEvent,server: str = "", limit:str = "15"):
        """剑三 金价 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.jinjia( self.serverdefault(server),limit))


    async def jx3_wujia(self, event: AstrMessageEvent,Name: str = "秃盒", server: str = ""):
        """剑三 物价 外观名称"""    
        return await self.T2I_image_msg(event, lambda: self.jx3fun.wujia(Name, self.serverdefault(server))) 


    async def jx3_jiaoyihang(self, event: AstrMessageEvent,Name: str = "守缺式",server: str = ""):
        """剑三 交易行 物品名称 服务器"""     
        return await self.T2I_image_msg(event, lambda: self.jx3fun.jiaoyihang(Name, self.serverdefault(server)))


    async def jx3_jueshemingpian(self, event: AstrMessageEvent, name: str = "飞翔大野猪", server: str = ""):
        """剑三 名片 角色 服务器"""
        return await self.image_msg(event, lambda: self.jx3fun.jueshemingpian( self.serverdefault(server),name)) 


    async def jx3_shuijimingpian(self, event: AstrMessageEvent,force: str = "万花", body: str = "萝莉", server: str = ""):
        """剑三 随机名片 职业 体型 服务器"""
        return await self.image_msg(event, lambda: self.jx3fun.shuijimingpian(force,body, self.serverdefault(server)))
 

    async def jx3_yanhuachaxun(self, event: AstrMessageEvent,name: str = "飞翔大野猪", server: str = ""):
        """剑三 烟花 角色 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.yanhuachaxun( self.serverdefault(server),name))


    async def jx3_dilujilu(self, event: AstrMessageEvent,server: str = ""):
        """剑三 的卢 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.dilujilu( self.serverdefault(server)))
  

    async def jx3_tuanduizhaomu(self, event: AstrMessageEvent,keyword: str = "25人普通会战弓月城", server: str = ""):
        """剑三 招募 副本 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.tuanduizhaomu( self.serverdefault(server),keyword))


    async def jx3_zhanji(self, event: AstrMessageEvent,name: str = "飞翔大野猪", server: str = "", mode:str = "33"):
        """剑三 战绩 角色 服务器 类型"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.zhanji(name, self.serverdefault(server),mode))


    async def jx3_qiyu(self, event: AstrMessageEvent,name: str = "飞翔大野猪", server: str = ""):
        """剑三 奇遇 角色名称 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.juesheqiyu(name, self.serverdefault(server)))
    

    async def jx3_zhengyingpaimai(self, event: AstrMessageEvent,name: str = "玄晶", server: str = ""):
        """剑三 阵营拍卖 物品名称 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3fun.zhengyingpaimai( self.serverdefault(server), name))
 

    async def jx3_fuyaojjiutian(self, event: AstrMessageEvent,server: str = ""):
        """剑三 扶摇九天 服务器"""
        return await self.plain_msg(event, lambda: self.jx3fun.fuyaojjiutian( self.serverdefault(server)))


    async def jx3_shuma(self, event: AstrMessageEvent,server: str = ""): 
        """剑三 刷马 服务器"""
        return await self.plain_msg(event, lambda: self.jx3fun.shuma( self.serverdefault(server)))


    async def jx3_pianzhi(self, event: AstrMessageEvent,qq: str):
        """剑三 骗子 QQ"""
        return await self.plain_msg(event, lambda: self.jx3fun.pianzhi(qq))


    async def jx3_bagua(self, event: AstrMessageEvent,name: str,text: str):
        """剑三 八卦 类型"""
        return await self.plain_msg(event, lambda: self.jx3fun.bagua(name))
    

    async def bilei_add(self, event: AstrMessageEvent,name: str, text: str):
        """避雷添加 名称 备注"""
        return await self.plain_msg(event, lambda: self.bilei.add(name,text,event.get_sender_name()))
    

    async def bilei_all(self, event: AstrMessageEvent):
        """避雷查看"""
        return await self.T2I_image_msg(event, self.bilei.all)
    

    async def bilei_select(self, event: AstrMessageEvent, name:str):
        """避雷查询"""
        return await self.T2I_image_msg(event, lambda: self.bilei.select(name))


    async def bilei_update(self, event: AstrMessageEvent, id:int, name: str, text: str):
        """避雷修改 ID 名称 备注"""
        return await self.plain_msg(event, lambda: self.bilei.update(id,name,text,event.get_sender_name()))


    async def bilei_delete(self, event: AstrMessageEvent, id:int):
        """避雷删除 ID"""
        return await self.plain_msg(event, lambda: self.bilei.delete(id))


    async def jx3_kaifhujiank(self, event: AstrMessageEvent):
        """剑三 开服监控"""     
        return_msg = await self.at.get_task_info("kfjk")
        yield event.plain_result(return_msg) 


    async def jx3_xinwenzhixun(self, event: AstrMessageEvent):
        """剑三 新闻推送"""     
        return_msg = await self.at.get_task_info("xwzx")
        yield event.plain_result(return_msg) 


    async def jx3_shuamamsg(self, event: AstrMessageEvent):
        """剑三 刷马推送"""     
        return_msg = await self.at.get_task_info("smxx")
        yield event.plain_result(return_msg) 


    async def jx3_chitusg(self, event: AstrMessageEvent):
        """剑三 赤兔推送"""     
        return_msg = await self.at.get_task_info("ctxx")
        yield event.plain_result(return_msg) 


