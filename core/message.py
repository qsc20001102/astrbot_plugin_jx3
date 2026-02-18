from astrbot.core import html_renderer
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.utils.session_waiter import (
    SessionController,
    session_waiter,
)

from .jx3_data import JX3Service
from .async_task import AsyncTask
from .bilei_data import BiLeidata


class MessageBuilder:
    """回复消息构建"""
    def __init__(self, server: str, jx3api: JX3Service, bilei: BiLeidata, jx3at: AsyncTask):
        self.server = server
        self.jx3api = jx3api
        self.bilei = bilei
        self.jx3at = jx3at


    async def html_render(
        self,
        tmpl: str,
        data: dict,
        return_url=True,
        options: dict | None = None,
    ) -> str:
        """渲染 HTML"""
        return await html_renderer.render_custom_template(
            tmpl,
            data,
            return_url=return_url,
            options=options,
        )
    

    def serverdefault(self,server) -> str:
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


    async def handler_plain_image_msg(self, event: AstrMessageEvent, action1, action2):
        """两轮会话消息发送通用，先文本列表等反馈序号在发送图片"""
        # 会话触发
        try:
            # 获取一轮数据
            data = await action1()
            if data["code"] == 200:
                # 发送一轮消息
                await event.send(event.plain_result(data["msg"])) 
                # 获取触发用户ID
                user_id = event.get_sender_id()

                # 二轮会话流程
                @session_waiter(timeout=30)
                async def macro_select_waiter(controller: SessionController,new_event: AstrMessageEvent):
                    # 跳过非触发用户消息
                    if new_event.get_sender_id() != user_id:
                        return
                    # 获取用户消息
                    msg = new_event.get_message_str().strip()
                    # 判断消息是否为数字
                    if not msg.isdigit():
                        await new_event.send(
                            MessageChain().message("输入异常，结束会话")
                        )
                        controller.stop()
                        return
                    # 判断数字是否在有效值内
                    num = int(msg)
                    if num < 1 or num > data["data"]["num"]:
                        await new_event.send(
                            MessageChain().message("无效序号，结束会话")
                        )
                        controller.stop()
                        return
                    
                    # 获取二轮数据
                    try:
                        data1 = await action2(data["data"]["list"][num])
                        if data1["code"] != 200:
                            await new_event.send(
                                MessageChain().message("获取详细数据失败")
                            )
                            controller.stop()
                            return
                        
                        # 消息拼接发送
                        chain = MessageChain()
                        msg_text = data1["data"]
                        chain.message(msg_text)
                        if data1["temp"] != "":
                            url = await self.html_render(data1["temp"], {}, options={})
                            chain.url_image(url)
                        await new_event.send(chain)

                    except Exception as e:
                        logger.error(f"功能函数执行错误: {e}")
                        await new_event.send(
                            MessageChain().message("猪脑过载，请稍后再试")
                        )

                    controller.stop()

                # 二轮会话激活
                try:
                    await macro_select_waiter(event)  
                except TimeoutError:
                    await event.send(event.plain_result("选择超时，已结束会话")) 
                except Exception:
                    logger.error("宏选择发生异常", exc_info=True)

            else:
                await event.send(event.plain_result(f"未搜索到相关内容")) 
                return
                
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试"))


    async def jx3_helps(self, event: AstrMessageEvent):
        """剑三 功能"""
        return await self.T2I_image_msg(event, self.jx3api.helps)


    async def jx3_richang(self, event: AstrMessageEvent,server: str = "" ,num: int = 0):
        """剑三 日常 服务器 天数"""
        return await self.plain_msg(event, lambda: self.jx3api.richang(self.serverdefault(server),num))


    async def jx3_richangyuche(self, event: AstrMessageEvent):
        """剑三 日常预测"""
        return await self.T2I_image_msg(event, self.jx3api.richangyuche)


    async def jx3_xingxiashijian(self, event: AstrMessageEvent,name: str = "穹野卫"):
        """剑三 名望"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.xingxiashijian(name))


    async def jx3_kaifu(self, event: AstrMessageEvent,server: str = ""):
        """剑三 开服 服务器"""
        return await self.plain_msg(event, lambda: self.jx3api.kaifu(self.serverdefault(server)))


    async def jx3_zhuangtai(self, event: AstrMessageEvent):
        """剑三 状态"""
        return await self.T2I_image_msg(event, self.jx3api.zhuangtai)

     
    async def jx3_shaohua(self, event: AstrMessageEvent,):
        """剑三 骚话"""
        return await self.plain_msg(event, self.jx3api.shaohua)


    async def jx3_jigai(self, event: AstrMessageEvent,):
        """剑三 技改"""
        return await self.plain_msg(event, self.jx3api.jigai)


    async def jx3_xinwen(self, event: AstrMessageEvent,num:int = 5):
        """剑三 新闻"""
        return await self.plain_msg(event, lambda: self.jx3api.xinwen(num))
 

    async def jx3_keju(self, event: AstrMessageEvent,subject: str, limit: int = 5):
        """剑三 科举"""
        return await self.plain_msg(event, lambda: self.jx3api.keju(subject,limit))


    async def jx3_huajia(self, event: AstrMessageEvent,  name: str= "", server: str = "", map: str= ""):
        """剑三 花价 名称 服务器 地图"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.huajia(self.serverdefault(server),name,map))


    async def jx3_zhuangshi(self, event: AstrMessageEvent,  name: str):
        """剑三 装饰 名称"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.zhuangshi(name))


    async def jx3_qiwu(self, event: AstrMessageEvent,  name: str):
        """剑三 器物 地图名称"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.qiwu(name))
            

    async def jx3_shapan(self, event: AstrMessageEvent,server: str = ""):
        """剑三 沙盘 服务器"""
        return await self.image_msg(event, lambda: self.jx3api.shapan(self.serverdefault(server)))  


    async def jx3_qufuqiyu(self, event: AstrMessageEvent,adventureName: str = "阴阳两界", server: str = ""):
        """剑三 奇遇统计 奇遇名称 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.qiyu(adventureName,self.serverdefault(server)))
 

    async def jx3_qiyugonglue(self, event: AstrMessageEvent,name: str):
        """剑三 奇遇攻略 奇遇名称"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.qiyugonglue(name))


    async def jx3_hong(self, event: AstrMessageEvent,name: str = "易筋经"):
        """剑三 宏 心法"""
        return await self.handler_plain_image_msg(event, lambda: self.jx3api.hong1(name), self.jx3api.hong2)


    async def jx3_peizhuang(self, event: AstrMessageEvent,name: str = "易筋经", tags: str = ""):
        """剑三 配装 心法"""
        return await self.plain_msg(event, lambda: self.jx3api.peizhuang( name,tags))


    async def jx3_jinjia(self, event: AstrMessageEvent,server: str = "", limit:str = "15"):
        """剑三 金价 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.jinjia( self.serverdefault(server),limit))


    async def jx3_wujia(self, event: AstrMessageEvent,Name: str = "秃盒", server: str = ""):
        """剑三 物价 外观名称"""    
        return await self.T2I_image_msg(event, lambda: self.jx3api.wujia(Name, self.serverdefault(server))) 


    async def jx3_jiaoyihang(self, event: AstrMessageEvent,Name: str = "守缺式",server: str = ""):
        """剑三 交易行 物品名称 服务器"""     
        return await self.T2I_image_msg(event, lambda: self.jx3api.jiaoyihang(Name, self.serverdefault(server)))


    async def jx3_jueshemingpian(self, event: AstrMessageEvent, name: str = "飞翔大野猪", server: str = ""):
        """剑三 名片 角色 服务器"""
        return await self.image_msg(event, lambda: self.jx3api.jueshemingpian( self.serverdefault(server),name)) 


    async def jx3_shuijimingpian(self, event: AstrMessageEvent,force: str = "万花", body: str = "萝莉", server: str = ""):
        """剑三 随机名片 职业 体型 服务器"""
        return await self.image_msg(event, lambda: self.jx3api.shuijimingpian(force,body, self.serverdefault(server)))
 

    async def jx3_yanhuachaxun(self, event: AstrMessageEvent,name: str = "飞翔大野猪", server: str = ""):
        """剑三 烟花 角色 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.yanhuachaxun( self.serverdefault(server),name))


    async def jx3_dilujilu(self, event: AstrMessageEvent,server: str = ""):
        """剑三 的卢 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.dilujilu( self.serverdefault(server)))
  

    async def jx3_tuanduizhaomu(self, event: AstrMessageEvent,keyword: str = "25人普通会战弓月城", server: str = ""):
        """剑三 招募 副本 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.tuanduizhaomu( self.serverdefault(server),keyword))


    async def jx3_zhanji(self, event: AstrMessageEvent,name: str = "飞翔大野猪", server: str = "", mode:str = "33"):
        """剑三 战绩 角色 服务器 类型"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.zhanji(name, self.serverdefault(server),mode))


    async def jx3_qiyu(self, event: AstrMessageEvent,name: str = "飞翔大野猪", server: str = ""):
        """剑三 奇遇 角色名称 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.juesheqiyu(name, self.serverdefault(server)))
    

    async def jx3_zhengyingpaimai(self, event: AstrMessageEvent,name: str = "玄晶", server: str = ""):
        """剑三 阵营拍卖 物品名称 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.zhengyingpaimai( self.serverdefault(server), name))
 

    async def jx3_fuyaojjiutian(self, event: AstrMessageEvent,server: str = ""):
        """剑三 扶摇九天 服务器"""
        return await self.plain_msg(event, lambda: self.jx3api.fuyaojjiutian( self.serverdefault(server)))


    async def jx3_shuma(self, event: AstrMessageEvent,server: str = ""): 
        """剑三 刷马 服务器"""
        return await self.plain_msg(event, lambda: self.jx3api.shuma( self.serverdefault(server)))


    async def jx3_pianzhi(self, event: AstrMessageEvent,qq: str):
        """剑三 骗子 QQ"""
        return await self.plain_msg(event, lambda: self.jx3api.pianzhi(qq))


    async def jx3_bagua(self, event: AstrMessageEvent,name: str = "818"):
        """剑三 八卦 类型"""
        return await self.plain_msg(event, lambda: self.jx3api.bagua(name))
    

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
        return_msg = await self.jx3at.get_task_info("kfts")
        await event.send(event.plain_result(return_msg)) 


    async def jx3_xinwenzhixun(self, event: AstrMessageEvent):
        """剑三 新闻推送"""     
        return_msg = await self.jx3at.get_task_info("xwts")
        await event.send(event.plain_result(return_msg)) 


    async def jx3_shuamamsg(self, event: AstrMessageEvent):
        """剑三 刷马推送"""     
        return_msg = await self.jx3at.get_task_info("smts")
        await event.send(event.plain_result(return_msg)) 


    async def jx3_chitusg(self, event: AstrMessageEvent):
        """剑三 赤兔推送"""     
        return_msg = await self.jx3at.get_task_info("ctts")
        await event.send(event.plain_result(return_msg)) 
