from typing import Any

from aiocqhttp.exceptions import ActionFailed
from astrbot.core import html_renderer
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.utils.session_waiter import (
    SessionController,
    session_waiter,
)

from .jx3api_data import JX3APIService
from .jx3box_data import JX3BOXService
from .event_push import EventPushService
from .bilei_data import BiLeidata


class MessageBuilder:
    """回复消息构建"""

    _RENDER_FORMATS = {"jpeg", "png"}
    _DEVICE_SCALE_FACTOR_LEVELS = {
        1.0: "normal",
        1.3: "high",
        1.8: "ultra",
    }
    def __init__(self, 
                 jx3api: JX3APIService, 
                 jx3box: JX3BOXService,  
                 bilei: BiLeidata, 
                 event_push: EventPushService,
                 icons: dict[str, dict[str, str]],
                 render_config: dict[str, Any] | None = None,
            ):
        self.jx3api = jx3api
        self.jx3box = jx3box
        self.bilei = bilei
        self.event_push = event_push
        self.icons = icons
        self.render_config = render_config if isinstance(render_config, dict) else {}


    def _build_render_options(
        self,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """根据插件配置构造 AstrBot HTML 截图参数。"""
        image_format = str(self.render_config.get("format", "jpeg")).lower()
        if image_format not in self._RENDER_FORMATS:
            image_format = "jpeg"

        try:
            device_scale_factor = float(
                self.render_config.get("device_scale_factor", 1.3)
            )
        except (TypeError, ValueError):
            device_scale_factor = 1.3
        scale_factor_level = self._DEVICE_SCALE_FACTOR_LEVELS.get(
            device_scale_factor,
            "high",
        )

        try:
            jpeg_quality = int(self.render_config.get("jpeg_quality", 100))
        except (TypeError, ValueError):
            jpeg_quality = 100
        jpeg_quality = max(1, min(100, jpeg_quality))

        options: dict[str, Any] = {
            "quality": jpeg_quality,
            "device_scale_factor_level": scale_factor_level,
            "scale": "device",
            "full_page": True,
            "omit_background": False,
            "type": image_format,
        }
        options.update(overrides or {})
        if options.get("type") == "png":
            options.pop("quality", None)
        return options


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
            options=self._build_render_options(options),
        )
    

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


    async def T2I_image_msg(
        self,
        event: AstrMessageEvent,
        action,
        render_options: dict | None = None,
    ):
        """最终将数据渲染成图片发送"""
        data = await action()
        try:
            if data["code"] == 200:
                data["data"]["icons"] = self.icons
                url = await self.html_render(
                    data["temp"],
                    data["data"],
                    options=render_options,
                )
                await event.send(event.image_result(url)) 
            else:
                await event.send(event.plain_result(data["msg"])) 

        except ActionFailed as e:
            if e.retcode == 1200:
                logger.warning(
                    "图片消息发送回执超时，消息可能已经成功送达，"
                    "不再发送错误提示。"
                )
                return
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试"))
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


    async def plain_chain(self, event: AstrMessageEvent, action):
        """富媒体消息"""
        data= await action()
        try:
            if data["code"] == 200:
                await event.send(event.chain_result(data["data"]))
            else:
                await event.send(event.plain_result(data["msg"])) 
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试")) 


    async def plain_image_msg(self, event: AstrMessageEvent, action):
        """发送正文文本，并把可选 HTML 正文渲染为附图。"""
        try:
            data = await action()
            if data.get("code") != 200:
                await event.send(
                    event.plain_result(data.get("msg") or "获取详细数据失败")
                )
                return

            chain = MessageChain()
            if data.get("data"):
                chain.message(str(data["data"]))
            if data.get("temp"):
                url = await self.html_render(data["temp"], {})
                chain.url_image(url)
            await event.send(chain)
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试"))


    async def handler_plain_image_msg(self, event: AstrMessageEvent, action1, action2, result_handler=None, timeout: int = 15):
        """通用两轮会话：首轮数字键值对裁剪后交给次轮函数。"""
        try:
            option_map = await action1()
            if not isinstance(option_map, dict) or not option_map:
                await event.send(event.plain_result("未搜索到可选内容"))
                return

            options = {str(key): value for key, value in option_map.items()}
            if not all(key.isdigit() for key in options):
                await event.send(event.plain_result("选项序号格式异常"))
                return

            menu_lines = [f"请选择序号（{timeout}后自动选择第一条）"]
            menu_lines.extend(
                f"{key}、{label}"
                for key, label in options.items()
            )
            await event.send(event.plain_result("\n".join(menu_lines)))
            user_id = event.get_sender_id()
            send_result = result_handler or self.T2I_image_msg

            async def send_selected(
                target_event: AstrMessageEvent,
                selected: dict[str, Any],
            ):
                await send_result(
                    target_event,
                    lambda: action2(selected),
                )

            @session_waiter(timeout=timeout)
            async def option_select_waiter(
                controller: SessionController,
                new_event: AstrMessageEvent,
            ):
                if new_event.get_sender_id() != user_id:
                    return

                msg = new_event.get_message_str().strip()
                if not msg.isdigit():
                    await new_event.send(MessageChain().message("输入异常，结束会话"))
                    controller.stop()
                    return

                choice = int(msg)
                choice_key = str(choice)
                if choice_key not in options:
                    await new_event.send(MessageChain().message("无效序号，结束会话"))
                    controller.stop()
                    return

                # 已取得有效选择，先结束等待计时，再执行可能超过 timeout 的
                # API 请求与图片渲染，避免超时分支重复发送默认第一项。
                controller.stop()
                try:
                    await send_selected(
                        new_event,
                        {choice_key: options[choice_key]},
                    )
                except Exception as e:
                    logger.error(f"二轮查询执行错误: {e}")
                    await new_event.send(MessageChain().message("猪脑过载，请稍后再试"))

            try:
                await option_select_waiter(event)
            except TimeoutError:
                first_key = next(iter(options))
                await send_selected(
                    event,
                    {first_key: options[first_key]},
                )
            except Exception:
                logger.error("二轮选择发生异常", exc_info=True)

        except (ValueError, RuntimeError) as e:
            await event.send(event.plain_result(str(e) or "未搜索到可选内容"))
        except Exception as e:
            logger.error(f"二轮会话执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试"))


    async def  helps(self, event: AstrMessageEvent):
        """ 功能"""
        return await self.T2I_image_msg(event, self.jx3api.helps)


    async def  richang(self, event: AstrMessageEvent, num: int = 0):
        """ 日常 天数"""
        return await self.plain_msg(event, lambda: self.jx3api.richang("day",num))


    async def  richangyuche(self, event: AstrMessageEvent):
        """ 日常预测"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.richang("list",15))


    async def  qiongyewei(self, event: AstrMessageEvent):
        """ 穹野卫"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.xingxiashijian("穹野卫"))
    
    async def  pifenghui(self, event: AstrMessageEvent):
        """ 披风会"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.xingxiashijian("披风会"))

    async def  yunchongshe(self, event: AstrMessageEvent):
        """ 云从社"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.xingxiashijian("云从社"))

    async def  chutianshe(self, event: AstrMessageEvent):
        """ 楚天社 """
        return await self.T2I_image_msg(event, lambda: self.jx3api.xingxiashijian("楚天社"))

    async def  guanaishouling(self, event: AstrMessageEvent):
        """ 关隘首领"""
        return await self.T2I_image_msg(event, self.jx3api.guanaishouling)

    async def  benrichitu(self, event: AstrMessageEvent):
        """ 本日赤兔"""
        return await self.plain_msg(event, self.jx3api.benrichitu)

    async def  benzhouchitu(self, event: AstrMessageEvent):
        """ 本周赤兔"""
        return await self.plain_msg(event, self.jx3api.benzhouchitu)

    async def  zhenyingevent(self, event: AstrMessageEvent, name:str = ""):
        """ 阵营事件 阵营"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.zhenyingevent(name,50))

    async def  yanhuachaxun(self, event: AstrMessageEvent,server: str,name: str = "" ):
        """ 烟花 服务器 角色"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.yanhuachaxun(server,name))

    async def  shuma(self, event: AstrMessageEvent,server: str ): 
        """ 刷马 服务器"""
        return await self.plain_msg(event, lambda: self.jx3api.shuma(server))

    async def  machang(self, event: AstrMessageEvent,server: str ): 
        """ 马场 服务器"""
        return await self.plain_msg(event, lambda: self.jx3api.machang(server,1))

    async def  zhanji(self, event: AstrMessageEvent, server: str ,name: str , mode:str = "33"):
        """ 战绩 服务器 角色 模式"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.zhanji(name, server,mode))

    async def  mingjianpaihang(self, event: AstrMessageEvent, mode:str = "33",limit: int = 50):
        """ 名剑排行 模式 数量 """
        return await self.T2I_image_msg(event, lambda: self.jx3api.mingjianpaihang(limit,mode))

    async def  mingjiantongji(self, event: AstrMessageEvent,mode: str = "33"):
        """ 名剑统计 模式"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.mingjiantongji(mode))

    async def banghuipaihang(self, event: AstrMessageEvent, server: str):
        """帮会排行 服务器。"""
        return await self.handler_plain_image_msg(
            event,
            lambda: self.jx3api.banghui_rank_menu(),
            lambda selected: self.jx3api.rank_statistical_select(server,selected,),
        )

    async def zhenyingpaihang(self, event: AstrMessageEvent, server: str):
        """阵营排行 服务器。"""
        return await self.handler_plain_image_msg(
            event,
            lambda: self.jx3api.zhenying_rank_menu(),
            lambda selected: self.jx3api.rank_statistical_select(server,selected,),
        )

    async def qitapaihang(self, event: AstrMessageEvent, server: str):
        """其他排行 服务器。"""
        return await self.handler_plain_image_msg(
            event,
            lambda: self.jx3api.qita_rank_menu(),
            lambda selected: self.jx3api.rank_statistical_select(server,selected,),
        )

    async def  shilianpaixing(self, event: AstrMessageEvent, server: str , name: str):
        """ 试炼排行 服务器 心法 """
        return await self.T2I_image_msg(event, lambda: self.jx3api.shilianpaixing(name, server))

    async def  zhengyingpaimai(self, event: AstrMessageEvent,server: str , name: str = "", limit: int = 50 ):
        """ 阵营拍卖 物品名称 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.zhengyingpaimai(server, name, limit))

    async def  dilujilu(self, event: AstrMessageEvent,server: str ):
        """ 的卢 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.dilujilu(server))

    async def  jinjia(self, event: AstrMessageEvent,server: str , limit:str = "15"):
        """ 金价 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.jinjia( server,limit))

    async def  wujia(self, event: AstrMessageEvent,Name: str , server: str = ""):
        """ 物价 外观名称 服务器"""    
        return await self.T2I_image_msg(event, lambda: self.jx3api.wujia(Name, server)) 

    async def  chengbeng(self, event: AstrMessageEvent, server: str ,Name: str ,source : int = 0):
        """ 成本 服务器 物品名称 """    
        return await self.T2I_image_msg(event, lambda: self.jx3api.chengbeng(Name, server,source)) 

    async def  kanhao(self, event: AstrMessageEvent,id: str):
        """ 看号 万宝楼编号 """    
        return await self.plain_msg(event, lambda: self.jx3api.bianhao(id)) 

    async def  bangzhanjilu(self, event: AstrMessageEvent, server: str):
        """ 帮战 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.bangzhanjilu(server))

    async def  shapan(self, event: AstrMessageEvent,server: str):
        """ 沙盘 服务器"""
        return await self.T2I_image_msg(
            event,
            lambda: self.jx3api.shapan(server),
            render_options={"omit_background": True, "type": "png"},
        )

    async def  zhueevent(self, event: AstrMessageEvent, server: str):
        """ 诛恶事件 服务器"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.zhueevent(server,20))

    async def  jueshemingpian(self, event: AstrMessageEvent, server: str , name: str , ):
        """ 名片 服务器 角色 """
        return await self.plain_chain(event, lambda: self.jx3api.jueshemingpian(server, name)) 

    async def  shuoyoumingpian(self, event: AstrMessageEvent, server: str, name: str, ):
        """ 全名片 服务器 角色 """
        return await self.plain_chain(event, lambda: self.jx3api.shuoyoumingpian(server,name)) 

    async def  shuijimingpian(self, event: AstrMessageEvent,server: str, force: str = "", body: str = "", ):
        """ 随机秀 服务器 门派 体型 """
        return await self.plain_chain(event, lambda: self.jx3api.shuijimingpian(server,force,body))

    async def  qiyuhuizong(self, event: AstrMessageEvent,server: str, num: str = "7" ):
        """ 汇总 服务器 天数 """
        return await self.T2I_image_msg(event, lambda: self.jx3api.qiyuhuizong(server, num))

    async def  weizuoqiyu(self, event: AstrMessageEvent,server: str, name: str, ):
        """ 未出 服务器 角色 """
        return await self.T2I_image_msg(event, lambda: self.jx3api.weizuoqiyu(server,name))

    async def  jinqiqiyu(self, event: AstrMessageEvent,server: str, limit: int = 20):
        """ 近期 服务器 数量"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.jinqiqiyu(server,limit))

    async def  juesheqiyu(self, event: AstrMessageEvent, server: str, name: str):
        """ 奇遇 服务器 角色 """
        return await self.T2I_image_msg(event, lambda: self.jx3api.juesheqiyu(server,name, 0))

    async def  qiyutongji(self, event: AstrMessageEvent,adventureName: str, server: str = "",limit: int = 20):
        """ 统计 奇遇 服务器 数量"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.qiyutongji(adventureName,server,limit))

    async def  qiyugonglue(self, event: AstrMessageEvent,name: str):
        """ 攻略 奇遇"""
        return await self.T2I_image_msg(event, lambda: self.jx3box.qiyugonglue(name))

    async def  jingnai(self, event: AstrMessageEvent, server: str, name: str):
        """ 精耐 服务器 角色 """
        return await self.T2I_image_msg(event, lambda: self.jx3api.jingnai(name, server))
    
    async def  baizhan(self, event: AstrMessageEvent):
        """ 百战"""
        return await self.T2I_image_msg(event, self.jx3api.baizhan)
    
    async def  chengjiu(self, event: AstrMessageEvent, server:str, role:str, name:str):
        """ 成就 服务器 角色 成就"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.chengjiuchaxun(server,role,name))

    async def  jueshe(self, event: AstrMessageEvent,server: str, name: str):
        """ 角色 服务器 名称 """
        return await self.plain_msg(event, lambda: self.jx3api.jueshe(server, name, 1))

    async def  zhenyan(self, event: AstrMessageEvent, name: str):
        """ 阵眼 心法"""
        return await self.plain_msg(event, lambda: self.jx3api.zhenyan(name))

    async def  peizhuang(self, event: AstrMessageEvent,name: str, tags: str = ""):
        """ 配装 心法 类型"""
        return await self.plain_msg(event, lambda: self.jx3box.peizhuang(name,tags))

    async def  zilipaixing(self, event: AstrMessageEvent, server: str = "", school: str = ""):
        """ 资历排行 服务器 门派 """
        return await self.T2I_image_msg(event, lambda: self.jx3api.zilipaixing(server, school))

    async def  jineng(self, event: AstrMessageEvent, name: str):
        """ 技能 心法"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.jineng(name,0))

    async def  qixue(self, event: AstrMessageEvent, name: str):
        """ 奇穴 心法"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.qixue(name,0))

    async def  liaotian(self, event: AstrMessageEvent, server:str, name: str, limit:int = 20, page:int = 1):
        """ 发言 服务器 角色 条数 页数"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.juesheliaotian(server,name,limit,page))

    async def  tongzhanyy(self, event: AstrMessageEvent, server: str = ""):
        """ 统战 服务器"""
        return await self.plain_msg(event, lambda: self.jx3api.tongzhanyy(server))

    async def  xiaoyao(self, event: AstrMessageEvent, name:str = ""):
        """ 小药 心法"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.xiaoyao(name))

    async def  pianzhi(self, event: AstrMessageEvent, uid: str, server:str = ""):
        """ 骗子 uid 服务器"""
        return await self.plain_msg(event, lambda: self.jx3api.pianzhi(server,uid))

    async def  huajia(self, event: AstrMessageEvent,  server: str, name: str= "" , map: str= ""):
        """ 花价 服务器 名称 地图"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.huajia(server,name,map))

    async def  zhuangshi(self, event: AstrMessageEvent,  name: str):
        """ 装饰 名称"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.zhuangshi(name))

    async def  qiwu(self, event: AstrMessageEvent,  name: str):
        """ 器物 地图名称"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.qiwu(name))

    async def  baishi(self, event: AstrMessageEvent, server: str, keyword: str = ""):
        """ 拜师 服务器 关键词 """
        return await self.T2I_image_msg(event, lambda: self.jx3api.shitu(2, server, keyword, 50))

    async def  shoutu(self, event: AstrMessageEvent, server: str, keyword: str = ""):
        """ 收徒 服务器 关键词 """
        return await self.T2I_image_msg(event, lambda: self.jx3api.shitu(1, server, keyword, 50))

    async def  weihu(self, event: AstrMessageEvent,limit:int = 5):
        """ 维护 数量"""
        return await self.plain_msg(event, lambda: self.jx3api.weihu(limit))

    async def  xinwen(self, event: AstrMessageEvent,limit:int = 5):
        """ 新闻 数量"""
        return await self.plain_msg(event, lambda: self.jx3api.xinwen(limit))

    async def  tuanduizhaomu(self, event: AstrMessageEvent,server: str, keyword: str = ""):
        """ 招募 服务器 副本"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.tuanduizhaomu( server,1,keyword,50))

    async def  tuanzhang(self, event: AstrMessageEvent,server: str, keyword: str = ""):
        """ 团长 服务器 名字"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.tuanduizhaomu( server,2,keyword,50))

    async def  tuanpai(self, event: AstrMessageEvent,server: str, keyword: str = ""):
        """ 团牌 服务器 内容"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.tuanduizhaomu( server,3,keyword,50))

    async def  daanzhishu(self, event: AstrMessageEvent):
        """ 答案之书"""
        return await self.plain_msg(event, self.jx3api.daanzhishu)

    async def  tiangou(self, event: AstrMessageEvent):
        """ 舔狗语录"""
        return await self.plain_msg(event, self.jx3api.tiangou)

    async def  fkxq4(self, event: AstrMessageEvent):
        """ 疯狂星期四"""
        return await self.plain_msg(event, lambda: self.jx3api.fengleiyulu("疯狂星期四"))

    async def  caihongpi(self, event: AstrMessageEvent):
        """ 彩虹屁"""
        return await self.plain_msg(event, lambda: self.jx3api.fengleiyulu("彩虹屁"))

    async def  dujitang(self, event: AstrMessageEvent):
        """ 毒鸡汤"""
        return await self.plain_msg(event, lambda: self.jx3api.fengleiyulu("毒鸡汤"))

    async def  pengyouquan(self, event: AstrMessageEvent):
        """ 朋友圈"""
        return await self.plain_msg(event, lambda: self.jx3api.fengleiyulu("朋友圈"))

    async def  heshengme(self, event: AstrMessageEvent,):
        """ 喝什么"""
        return await self.plain_msg(event, self.jx3api.heshengme)

    async def  chishengme(self, event: AstrMessageEvent,):
        """ 吃什么"""
        return await self.plain_msg(event, self.jx3api.chishengme)

    async def  shaohua(self, event: AstrMessageEvent,):
        """ 骚话"""
        return await self.plain_msg(event, self.jx3api.shaohua)

    async def  zhananyulu(self, event: AstrMessageEvent,):
        """ 渣男语录"""
        return await self.plain_msg(event, self.jx3api.zhananyulu)

    async def  tiebawujia(self, event: AstrMessageEvent, name: str, server: str = "", limit: str = "5", ):
        """ 贴吧物价 名称 服务器 数量 """
        return await self.plain_msg(event, lambda: self.jx3api.tiebawujia(name, server, limit))

    async def  bagua(self, event: AstrMessageEvent, server:str = "", limit:str = 10):
        """ 818 """
        return await self.plain_msg(event, lambda: self.jx3api.bagua(818,server,limit))

    async def  keju(self, event: AstrMessageEvent,subject: str, limit: int = 5):
        """ 科举 题目 条数"""
        return await self.plain_msg(event, lambda: self.jx3api.keju(subject,limit))

    async def  zhuangtai(self, event: AstrMessageEvent):
        """ 区服"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.zhuangtai(""))

    async def  kaifu(self, event: AstrMessageEvent,server: str):
        """ 开服 服务器"""
        return await self.plain_msg(event, lambda: self.jx3api.kaifu(server))

    async def  jigai(self, event: AstrMessageEvent,):
        """ 技改"""
        return await self.plain_msg(event, self.jx3api.jigai)

    async def  jiemi(self, event: AstrMessageEvent):
        """ 解密"""
        return await self.plain_msg(event, self.jx3api.jiemi)

    async def  fubeng(self, event: AstrMessageEvent, server:str, name:str):
        """ 副本"""
        return await self.T2I_image_msg(event, lambda: self.jx3api.fubengjilu(server,name))

    async def  diaoluo(self, event: AstrMessageEvent, name: str,  server: str = "", limit: str = "20",):
        """ 掉落 物品 服务器 数量 """
        return await self.T2I_image_msg(event, lambda: self.jx3api.diaoluo(name, server, limit))


    async def  hong(self, event: AstrMessageEvent,name: str):
        """ 宏 心法"""
        return await self.handler_plain_image_msg(
            event,
            lambda: self.jx3box.hong1(name),
            lambda selected: self.jx3box.hong_select(name, selected),
            result_handler=self.plain_image_msg,
        )

    async def  zili(self, event: AstrMessageEvent, server: str, name: str):
        """ 资历 角色名称 服务器"""
        return await self.handler_plain_image_msg(
            event,
            lambda: self.jx3api.zili_menu(),
            lambda selected: self.jx3api.zili(server, name, selected),
        )

    async def  jiaoyihang(self, event: AstrMessageEvent,server: str, Name: str):
        """ 交易行 物品名称 服务器"""     
        return await self.T2I_image_msg(event, lambda: self.jx3box.jiaoyihang(Name,server))


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


    async def shijian_tuisong(
        self,
        event: AstrMessageEvent,
        first: str = "",
        second: str = "",
    ):
        """管理当前会话的实时事件订阅。"""
        return_msg = await self.event_push.configure(
            event.unified_msg_origin,
            first,
            second,
        )
        await event.send(event.plain_result(return_msg))
