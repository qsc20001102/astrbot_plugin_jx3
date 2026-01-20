# pyright: reportOptionalMemberAccess=false

import json
import shutil
import pathlib
import asyncio
from pathlib import Path
from typing import Union

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api import AstrBotConfig
import astrbot.api.message_components as Comp

from .core.jx3_service import JX3Service
from .core.async_task import AsyncTask


@register("astrbot_plugin_jx3", 
          "fxdyz", 
          "通过接口调用剑网三API接口获取游戏数据", 
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
        self.server = self.conf.get("server", "梦江南")
        logger.info(f"配置加载默认服务器：{self.server}")
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
        except Exception as e:
            if hasattr(self, "at"):
                await self.at.destroy()  
            logger.error(f"功能模块初始化失败: {e}")
            raise

        logger.info("jx3api 异步插件初始化完成")


    def check_and_copy_db(self, local_data_dir: Union[str, Path], db_filename: str, default_db_dir: Union[str, Path]) -> pathlib.Path:
        """
        检查本地数据目录中是否存在指定的数据库文件。
        如果不存在，则从默认目录复制该文件。
        Args:
            local_data_dir: 目标数据库文件所在的文件夹路径。
            db_filename: 数据库文件的名称 (例如: 'local_data.db')。
            default_db_dir: 默认/源数据库文件所在的文件夹路径。
        Returns:
            最终的数据库文件的完整 pathlib.Path 对象。
        Raises:
            FileNotFoundError: 如果默认的源数据库文件不存在。
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


    @filter.command_group("剑三")
    def jx3(self):
        pass


    @jx3.command("功能")
    async def jx3_helps(self, event: AstrMessageEvent):
        """剑三 功能"""
        data = await self.jx3fun.helps()
        try:
            
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @jx3.command("日常")
    async def jx3_richang(self, event: AstrMessageEvent,server: str = "" ,num: int = 0):
        """剑三 日常 服务器 天数"""
        try:
            data= await self.jx3fun.richang(self.serverdefault(server),num)
            if data["code"] == 200:
                yield event.plain_result(data["data"])
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")
    

    @jx3.command("日常预测")
    async def jx3_richangyuche(self, event: AstrMessageEvent):
        """剑三 日常预测"""
        try:
            data= await self.jx3fun.richangyuche()
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")


    @jx3.command("名望")
    async def jx3_xingxiashijian(self, event: AstrMessageEvent,name: str = "穹野卫"):
        """剑三 名望"""
        try:
            data= await self.jx3fun.xingxiashijian(name)
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")


    @jx3.command("开服")
    async def jx3_kaifu(self, event: AstrMessageEvent,server: str = ""):
        """剑三 开服 服务器"""
        try:
            data= await self.jx3fun.kaifu(self.serverdefault(server))
            if data["code"] == 200:
                yield event.plain_result(data["data"])
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")


    @jx3.command("状态")
    async def jx3_zhuangtai(self, event: AstrMessageEvent):
        """剑三 状态"""
        try:
            data= await self.jx3fun.zhuangtai()
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")
     

    @jx3.command("骚话")
    async def jx3_shaohua(self, event: AstrMessageEvent,):
        """剑三 骚话"""
        try:
            data= await self.jx3fun.shaohua()
            if data["code"] == 200:
                yield event.plain_result(data["data"])
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @jx3.command("技改")
    async def jx3_jigai(self, event: AstrMessageEvent,):
        """剑三 技改"""
        try:
            data= await self.jx3fun.jigai()
            if data["code"] == 200:
                yield event.plain_result(data["data"])
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 
 

    @jx3.command("沙盘")
    async def jx3_shapan(self, event: AstrMessageEvent,server: str = ""):
        """剑三 沙盘 服务器"""
        try:
            data= await self.jx3fun.shapan(self.serverdefault(server))
            if data["code"] == 200:
                yield event.image_result(data["data"])
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")   


    @jx3.command("奇遇统计")
    async def jx3_qufuqiyu(self, event: AstrMessageEvent,adventureName: str = "阴阳两界", server: str = ""):
        """剑三 奇遇统计 奇遇名称 服务器"""
        try:
            data= await self.jx3fun.qiyu(adventureName,self.serverdefault(server))
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @jx3.command("奇遇攻略")
    async def jx3_qiyugonglue(self, event: AstrMessageEvent,name: str):
        """剑三 奇遇攻略 奇遇名称"""
        try:
            data= await self.jx3fun.qiyugonglue(name)
            if data["code"] == 200:
                url = await self.html_render(data["temp"], {}, options={})
                chain = [
                    Comp.Plain(f"{data['data']} \n"),
                    Comp.Image.fromURL(f"{url}")
                ]
                yield event.chain_result(chain)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")


    @jx3.command("金价")
    async def jx3_jinjia(self, event: AstrMessageEvent,server: str = "", limit:str = "15"):
        """剑三 金价 服务器"""
        try:
            data= await self.jx3fun.jinjia( self.serverdefault(server),limit)
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")


    @jx3.command("物价")
    async def jx3_wujia(self, event: AstrMessageEvent,Name: str = "秃盒", server: str = ""):
        """剑三 物价 外观名称"""     
        try:
            data=await self.jx3fun.wujia(Name, self.serverdefault(server))
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @jx3.command("交易行")
    async def jx3_jiaoyihang(self, event: AstrMessageEvent,Name: str = "守缺式",server: str = ""):
        """剑三 交易行 物品名称 服务器"""     
        try:
            data=await self.jx3fun.jiaoyihang(Name, self.serverdefault(server))
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
                
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @jx3.command("名片")
    async def jx3_jueshemingpian(self, event: AstrMessageEvent, name: str = "飞翔大野猪", server: str = ""):
        """剑三 名片 角色 服务器"""
        try:
            data= await self.jx3fun.jueshemingpian( self.serverdefault(server),name)
            if data["code"] == 200:
                chain = [
                    Comp.Plain(f"{data['data']['serverName']}--{data['data']['roleName']} \n"),
                    Comp.Image.fromURL(f"{data['data']['showAvatar']}")
                ]
                yield event.chain_result(chain)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")  


    @jx3.command("随机名片")
    async def jx3_shuijimingpian(self, event: AstrMessageEvent,force: str = "万花", body: str = "萝莉", server: str = ""):
        """剑三 随机名片 职业 体型 服务器"""
        try:
            data= await self.jx3fun.shuijimingpian(force,body, self.serverdefault(server))
            if data["code"] == 200:
                chain = [
                    
                    Comp.Plain(f"{data['data']['serverName']}--{data['data']['roleName']} \n"),
                    Comp.Image.fromURL(f"{data['data']['showAvatar']}"),
                    Comp.Plain(f"{force}--{body} \n")
                ]
                yield event.chain_result(chain)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")  


    @jx3.command("烟花")
    async def jx3_yanhuachaxun(self, event: AstrMessageEvent,name: str = "飞翔大野猪", server: str = ""):
        """剑三 烟花 角色 服务器"""
        try:
            data= await self.jx3fun.yanhuachaxun( self.serverdefault(server),name)
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")  


    @jx3.command("的卢")
    async def jx3_dilujilu(self, event: AstrMessageEvent,server: str = ""):
        """剑三 的卢 服务器"""
        try:
            data= await self.jx3fun.dilujilu( self.serverdefault(server))
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")  


    @jx3.command("招募")
    async def jx3_tuanduizhaomu(self, event: AstrMessageEvent,keyword: str = "25人普通会战弓月城", server: str = ""):
        """剑三 招募 副本 服务器"""
        try:
            data= await self.jx3fun.tuanduizhaomu( self.serverdefault(server),keyword)
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @jx3.command("战绩")
    async def jx3_zhanji(self, event: AstrMessageEvent,name: str = "飞翔大野猪", server: str = "", mode:str = "33"):
        """剑三 战绩 角色 服务器 类型"""
        try:
            data= await self.jx3fun.zhanji(name, self.serverdefault(server),mode)
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @jx3.command("奇遇")
    async def jx3_qiyu(self, event: AstrMessageEvent,name: str = "飞翔大野猪", server: str = ""):
        """剑三 奇遇 角色名称 服务器"""
        try:
            data= await self.jx3fun.juesheqiyu(name, self.serverdefault(server))
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @jx3.command("阵营拍卖")
    async def jx3_zhengyingpaimai(self, event: AstrMessageEvent,name: str = "玄晶", server: str = ""):
        """剑三 阵营拍卖 物品名称 服务器"""
        try:
            data= await self.jx3fun.zhengyingpaimai( self.serverdefault(server), name)
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @jx3.command("扶摇九天")
    async def jx3_fuyaojjiutian(self, event: AstrMessageEvent,server: str = ""):
        """剑三 扶摇九天 服务器"""
        try:
            data= await self.jx3fun.fuyaojjiutian( self.serverdefault(server))
            if data["code"] == 200:
                yield event.plain_result(data["data"])
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")


    @jx3.command("刷马")
    async def jx3_shuma(self, event: AstrMessageEvent,server: str = ""): 
        """剑三 刷马 服务器"""
        try:
            data= await self.jx3fun.shuma( self.serverdefault(server))
            if data["code"] == 200:
                yield event.plain_result(data["data"])
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")


    @jx3.command("骗子")
    async def jx3_pianzhi(self, event: AstrMessageEvent,qq: str):
        """剑三 骗子 QQ"""
        try:
            data= await self.jx3fun.pianzhi(qq)
            if data["code"] == 200:
                yield event.plain_result(data["data"])
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")


    @jx3.command("八卦")
    async def jx3_bagua(self, event: AstrMessageEvent,type: str):
        """剑三 八卦 类型"""
        try:
            data= await self.jx3fun.bagua(type)
            if data["code"] == 200:
                yield event.plain_result(data["data"])
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")


    @jx3.command("开服监控")
    async def jx3_kaifhujiank(self, event: AstrMessageEvent):
        """剑三 开服监控"""     
        return_msg = await self.at.get_task_info("kfjk")
        yield event.plain_result(return_msg) 


    @jx3.command("新闻推送")
    async def jx3_xinwenzhixun(self, event: AstrMessageEvent):
        """剑三 新闻推送"""     
        return_msg = await self.at.get_task_info("xwzx")
        yield event.plain_result(return_msg) 


    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        if self.at:
            await self.at.destroy()
            self.at = None

        if self.jx3fun:
            await self.jx3fun.close()
            self.jx3fun = None
        logger.info("jx3api插件已卸载/停用")