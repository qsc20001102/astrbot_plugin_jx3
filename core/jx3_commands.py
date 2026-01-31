# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
import json
import shutil
import pathlib
import inspect
from pathlib import Path
from typing import Union
import asyncio

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api import AstrBotConfig
import astrbot.api.message_components as Comp
from astrbot.core.utils.session_waiter import (
    SessionController,
    session_waiter,
)

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


    async def jx3_bagua(self, event: AstrMessageEvent,type: str):
        """剑三 八卦 类型"""
        return await self.plain_msg(event, lambda: self.jx3fun.bagua(type))


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