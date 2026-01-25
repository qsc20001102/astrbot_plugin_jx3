# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportIndexIssue=false
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

from .jx3_data import JX3Service
from .async_task import AsyncTask


class JX3Commands(Star):
    def __init__(self, jx3_data:JX3Service, at:AsyncTask, server:str):
        self.jx3fun = jx3_data
        self.jx3at = at
        self.server = server


    def serverdefault(self,server):
        """加载配置默认服务器"""
        if server == "":
            return self.server
        return server


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
 

    async def jx3_keju(self, event: AstrMessageEvent,subject: str, limit: int = 5):
        """剑三 科举"""
        try:
            data= await self.jx3fun.keju(subject,limit)
            if data["code"] == 200:
                yield event.plain_result(data["data"])
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    async def jx3_huajia(self, event: AstrMessageEvent,  name: str= "", server: str = "", map: str= ""):
        """剑三 花价 名称 服务器 地图"""
        try:
            data= await self.jx3fun.huajia(self.serverdefault(server),name,map)
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")


    async def jx3_zhuangshi(self, event: AstrMessageEvent,  name: str):
        """剑三 装饰 名称"""
        try:
            data= await self.jx3fun.zhuangshi(name)
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")


    async def jx3_qiwu(self, event: AstrMessageEvent,  name: str):
        """剑三 器物 地图名称"""
        try:
            data= await self.jx3fun.qiwu(name)
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试")            


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


    async def jx3_kaifhujiank(self, event: AstrMessageEvent):
        """剑三 开服监控"""     
        return_msg = await self.jx3at.get_task_info("kfjk")
        yield event.plain_result(return_msg) 


    async def jx3_xinwenzhixun(self, event: AstrMessageEvent):
        """剑三 新闻推送"""     
        return_msg = await self.jx3at.get_task_info("xwzx")
        yield event.plain_result(return_msg) 


    async def jx3_shuamamsg(self, event: AstrMessageEvent):
        """剑三 刷马推送"""     
        return_msg = await self.jx3at.get_task_info("smxx")
        yield event.plain_result(return_msg) 


    async def jx3_chitusg(self, event: AstrMessageEvent):
        """剑三 赤兔推送"""     
        return_msg = await self.jx3at.get_task_info("ctxx")
        yield event.plain_result(return_msg) 