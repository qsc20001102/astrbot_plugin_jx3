import inspect
from pathlib import Path
from sys import maxsize
from typing import cast

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from .core.sqlite import AsyncSQLiteDB
from .core.jx3api_data import JX3APIService
from .core.jx3box_data import JX3BOXService
from .core.event_push import EventPushService
from .core.bilei_data import BiLeidata
from .core.kungfu_alias import KungfuAliasService
from .core.server_binding import ServerBindingService
from .core.session_control import SessionControlService
from .core.webui import WebUIService
from .core.message import MessageBuilder
from .core.fun_basic import load_as_base64


PLUGIN_NAME = "astrbot_plugin_jx3"

@register("astrbot_plugin_jx3", 
          "fxdyz", 
          "聚合剑网三游戏数据，提供查询、图片渲染、本地避雷和实时事件推送。",
          "3.4.5",
          "https://github.com/qsc20001102/astrbot_plugin_jx3"
)
class Jx3ApiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 获取插件配置
        self.conf = config

        # 指令前缀
        self.prefix = self.conf.get("prefix",{})
        if self.prefix.get("enable"):
            logger.info(f"已启用指令前缀功能，前缀为：{self.prefix.get('text')}")
        else:
            logger.info(f"未启用指令前缀功能。")

        # 获取数据文件路径
        self.get_data_path()
        # 加载图片base64编码
        self.load_local_base64()
        # 构造所有类
        self.create_all()
        # 注册插件管理页接口
        self.webui.register(context, PLUGIN_NAME)


        # 声明指令集
        self.command_map = {}

        logger.info("jx3api插件初始化完成")


    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""     
        try:
            # 数据库初始化
            await self.init_bilei_data()
            await self.init_trade_item_cache_data()
            await self.kungfu_alias.initialize()
            await self.server_binding.initialize()
            await self.session_control.initialize()

            # 获取区服目录，用于识别完整参数与区服别名。
            await self.server_binding.update_server_catalog(
                await self.jx3api.server_list()
            )

            # 开启实时事件通道
            await self.event_push.initialize()

        except Exception as e:
            if self.event_push is not None:
                await self.event_push.stop()
            logger.exception("功能模块初始化失败")
            raise

        # 指令集
        self.ini_command_map()

        logger.info("jx3api 异步插件初始化完成")


    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        
        if self.event_push:
            await self.event_push.stop()

        if self.jx3api:
            await self.jx3api.close()

        if self.jx3box:
            await self.jx3box.close()

        if self.local_sql_db:
            await self.local_sql_db.close()
            
        logger.info("jx3api插件已卸载/停用")


    def get_data_path(self):
        """获取数据文件路径"""
        # 本地数据存储路径
        self.local_data_dir = StarTools.get_data_dir("astrbot_plugin_jx3")
        # 插件数据存储路径
        self.plugin_data_dir = Path(__file__).parent / "data"
        self.plugin_temp_dir = Path(__file__).parent /"templates"

        # SQLite本地路径
        self.local_data_path = self.local_data_dir / "local_data.db"
        self.kungfu_seed_path = self.plugin_data_dir / "kungfu.json"
        self.server_alias_seed_path = self.plugin_data_dir / "server_aliases.json"

        # 图片文件路径
        self.plugin_temp_img = self.plugin_temp_dir / "img"
        self.plugin_temp_sand = self.plugin_temp_img / "sand"
        self.plugin_temp_sect = self.plugin_temp_dir / "sect"
        self.plugin_temp_serendipity = self.plugin_temp_dir / "serendipity"

        # 数据路径打印
        logger.debug(f"本地数据路径: {self.local_data_path}")
        logger.debug(f"心法种子数据路径: {self.kungfu_seed_path}")
        logger.debug(f"区服别名种子数据路径: {self.server_alias_seed_path}")
        logger.debug(f"图片文件路径: {self.plugin_temp_img}")
        logger.debug(f"沙盘图片文件路径: {self.plugin_temp_sand}")
        logger.debug(f"图片文件路径: {self.plugin_temp_sect}")
        logger.debug(f"图片文件路径: {self.plugin_temp_serendipity}")


    def load_local_base64(self):
        """加载图片文件的base64编码"""
        img = load_as_base64(str(self.plugin_temp_img))
        sand = load_as_base64(str(self.plugin_temp_sand))
        sect = load_as_base64(str(self.plugin_temp_sect))
        serendipity = load_as_base64(str(self.plugin_temp_serendipity))
        self.icons =  {
            "img": img,
            "sand": sand,
            "sect": sect,
            "serendipity": serendipity
        }        
        logger.debug(f"图片base64编码加载完成")


    def create_all(self):
        """构造所有类"""
        # 数据库实例化
        self.local_sql_db = AsyncSQLiteDB(str(self.local_data_path))
        # 剑网三功能实例化
        self.bilei = BiLeidata(self.local_sql_db)
        self.jx3api = JX3APIService(self.conf, self.local_sql_db)
        self.jx3box = JX3BOXService(self.conf, self.local_sql_db, self.local_sql_db)
        self.kungfu_alias = KungfuAliasService(
            self.local_sql_db,
            self.kungfu_seed_path,
        )
        self.server_binding = ServerBindingService(
            self.local_sql_db,
            self.server_alias_seed_path,
        )
        self.session_control = SessionControlService(self.local_sql_db)
        self.event_push = EventPushService(
            cast(Context, self.context),
            self.conf,
            self.local_sql_db,
            self.server_binding,
            self.session_control,
        )
        self.webui = WebUIService(
            self.jx3api,
            self.event_push,
            self.server_binding,
            self.kungfu_alias,
            self.session_control,
        )
        self.jx3cmd = MessageBuilder(
            self.jx3api,
            self.jx3box,
            self.bilei,
            self.event_push,
            self.icons,
            self.conf.get("image_render_quality", {}),
        )


    async def init_bilei_data(self):
        """初始化避雷数据表"""
        # 连接本地数据
        await self.local_sql_db.connect()
        # 创建bilei表
        await self.local_sql_db.execute("""
        CREATE TABLE IF NOT EXISTS bilei(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            text TEXT,
            time TEXT,
            user TEXT                                           
        )
        """)
    

    async def init_trade_item_cache_data(self):
        """初始化交易行物品缓存，并清理已停用的资历缓存表。"""
        await self.local_sql_db.execute("""
        CREATE TABLE IF NOT EXISTS trade_item_cache(
            key TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        legacy_cache = await self.local_sql_db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("achievement_cache",),
        )
        if legacy_cache:
            # 旧表曾与交易行共用；仅迁移仍有效的交易行缓存后移除资历缓存。
            await self.local_sql_db.execute(
                """
                INSERT OR IGNORE INTO trade_item_cache (key, content, updated_at)
                SELECT key, content, updated_at
                FROM achievement_cache
                WHERE key = ?
                """,
                ("trade_item_groups",),
            )
            await self.local_sql_db.execute("DROP TABLE achievement_cache")


    def ini_command_map(self):
        """初始化指令集"""
        self.command_map = {
            "功能": self. jx3cmd.helps,
            "日常": self. jx3cmd.richang,
            "日常预测": self. jx3cmd.richangyuche,
            "穹野卫": self. jx3cmd.qiongyewei,
            "披风会": self. jx3cmd.pifenghui,
            "云从社": self. jx3cmd.yunchongshe,
            "楚天社": self. jx3cmd.chutianshe,
            "关隘": self. jx3cmd.guanaishouling,
            "赤兔": self. jx3cmd.benrichitu,
            "本周赤兔": self. jx3cmd.benzhouchitu,
            "阵营奉献": self. jx3cmd.zhenyingevent,
            "烟花": self. jx3cmd.yanhuachaxun,
            "刷马": self. jx3cmd.shuma,
            "马场": self. jx3cmd.machang,
            "战绩": self. jx3cmd.zhanji,
            "名剑排行": self. jx3cmd.mingjianpaihang,
            "名剑统计": self. jx3cmd.mingjiantongji,
            "跨服名剑": self.jx3cmd.kuafumingjian,
            "武林争霸": self.jx3cmd.wulinzhengba,
            "捕快荣誉": self.jx3cmd.bukairongyu,
            "江湖浪客": self.jx3cmd.jianghulangke,
            "决斗挑战": self.jx3cmd.juedoutiaozhan,
            "帮会排行": self. jx3cmd.banghuipaihang,
            "阵营排行": self. jx3cmd.zhenyingpaihang,
            "其他排行": self. jx3cmd.qitapaihang,
            "试炼排行": self. jx3cmd.shilianpaixing,
            "资历": self. jx3cmd.zili,
            "阵营拍卖": self. jx3cmd.zhengyingpaimai,
            "的卢": self. jx3cmd.dilujilu,
            "金价": self. jx3cmd.jinjia,
            "物价": self. jx3cmd.wujia,
            "成本": self. jx3cmd.chengbeng,
            "看号": self. jx3cmd.kanhao,
            "帮战": self. jx3cmd.bangzhanjilu,
            "沙盘": self. jx3cmd.shapan,
            "诛恶": self. jx3cmd.zhueevent,
            "名片": self. jx3cmd.jueshemingpian,
            "全名片": self. jx3cmd.shuoyoumingpian,
            "随机秀": self. jx3cmd.shuijimingpian,
            "奇遇": self. jx3cmd.juesheqiyu,
            "查询": self. jx3cmd.juesheqiyu,
            "未出": self. jx3cmd.weizuoqiyu,
            "汇总": self. jx3cmd.qiyuhuizong,
            "近期": self. jx3cmd.jinqiqiyu,
            "统计": self. jx3cmd.qiyutongji,
            "攻略": self. jx3cmd.qiyugonglue,
            "精耐": self. jx3cmd.jingnai,
            "百战": self. jx3cmd.baizhan,
            "成就": self. jx3cmd.chengjiu,
            "角色": self. jx3cmd.jueshe,
            "阵眼": self. jx3cmd.zhenyan,
            "配装": self. jx3cmd.peizhuang,
            "资历排行": self. jx3cmd.zilipaixing,
            "技能": self. jx3cmd.jineng,
            "奇穴": self. jx3cmd.qixue,
            "发言": self. jx3cmd.liaotian,
            "统战": self. jx3cmd.tongzhanyy,
            "小药": self. jx3cmd.xiaoyao,
            "骗子": self. jx3cmd.pianzhi,
            "花价": self. jx3cmd.huajia,
            "装饰": self. jx3cmd.zhuangshi,
            "器物": self. jx3cmd.qiwu,
            "拜师": self. jx3cmd.baishi,
            "收徒": self. jx3cmd.shoutu,
            "维护": self. jx3cmd.weihu,
            "新闻": self. jx3cmd.xinwen,
            "招募": self. jx3cmd.tuanduizhaomu,
            "团长": self. jx3cmd.tuanzhang,
            "团牌": self. jx3cmd.tuanpai,
            "答案之书": self. jx3cmd.daanzhishu,
            "舔狗语录": self. jx3cmd.tiangou,
            "疯狂星期四": self. jx3cmd.fkxq4,
            "彩虹屁": self. jx3cmd.caihongpi,
            "毒鸡汤": self. jx3cmd.dujitang,
            "朋友圈": self. jx3cmd.pengyouquan,
            "喝什么": self. jx3cmd.heshengme,
            "吃什么": self. jx3cmd.chishengme,
            "骚话": self. jx3cmd.shaohua,
            "渣男语录": self. jx3cmd.zhananyulu,
            "贴吧物价": self. jx3cmd.tiebawujia,
            "818": self. jx3cmd.bagua,
            "科举": self. jx3cmd.keju,
            "区服": self. jx3cmd.zhuangtai,
            "开服": self. jx3cmd.kaifu,
            "技改": self. jx3cmd.jigai,
            "解密": self. jx3cmd.jiemi,
            "掉落": self. jx3cmd.diaoluo,

            "宏": self. jx3cmd.hong,
            "交易行": self. jx3cmd.jiaoyihang,

            "绑定区服": self.bind_server,
            "解绑区服": self.unbind_server,
            
            "事件推送": self.jx3cmd.shijian_tuisong,

            "避雷添加": self.jx3cmd.bilei_add,
            "避雷查看": self.jx3cmd.bilei_all,
            "避雷查询": self.jx3cmd.bilei_select,
            "避雷修改": self.jx3cmd.bilei_update,
            "避雷删除": self.jx3cmd.bilei_delete,
        }


    def parse_message(self, text: str) -> list[str] | None:
        """消息解析"""
        text = text.strip()
        if not text:
            return None

        # 前缀模式
        if self.prefix.get("enable"):
            prefix = str(self.prefix.get("text") or "").strip()
            if not prefix:
                return None
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
            else:
                # 非前缀消息，直接忽略
                return None

        return text.split()

    def resolve_command(self, event: AstrMessageEvent):
        """从 AstrBot 处理后文本和平台原始文本中识别本插件指令。"""
        processed_text = event.message_str
        original_text = getattr(event.message_obj, "message_str", "")
        seen = set()

        for text in (processed_text, original_text):
            if not isinstance(text, str):
                continue

            text = text.strip()
            if not text or text in seen:
                continue
            seen.add(text)

            parts = self.parse_message(text)
            if not parts:
                continue

            cmd, *args = parts
            handler = self.command_map.get(cmd)
            if handler:
                return cmd, args, handler

        return None

    async def _prepare_server_args(
        self,
        handler,
        event: AstrMessageEvent,
        args: list[str],
    ) -> list[str]:
        """补齐会话绑定、解析区服别名，并支持用“全区”显式传空区服。"""
        params = [
            parameter
            for parameter in inspect.signature(handler).parameters.values()
            if parameter.name not in {"self", "event"}
        ]
        server_index = next(
            (index for index, parameter in enumerate(params) if parameter.name == "server"),
            None,
        )
        if server_index is None:
            return args

        prepared = list(args)
        bound_server = await self.server_binding.get_binding(
            event.unified_msg_origin
        )
        has_server_arg = server_index < len(prepared)

        if bound_server:
            explicit_server = (
                has_server_arg
                and (
                    self.server_binding.is_all_servers_query(
                        prepared[server_index]
                    )
                    or self.server_binding.is_known_server(prepared[server_index])
                )
            )
            if explicit_server:
                prepared[server_index] = self.server_binding.resolve_query_server(
                    prepared[server_index]
                )
            else:
                prepared.insert(server_index, bound_server)
        elif has_server_arg:
            prepared[server_index] = self.server_binding.resolve_query_server(
                prepared[server_index]
            )

        return prepared

    def _prepare_kungfu_args(self, handler, args: list[str]) -> list[str]:
        """Resolve the kungfu parameter through the global alias catalog.

        Args:
            handler: Command handler whose signature defines argument positions.
            args: Positional command arguments after server preparation.

        Returns:
            Arguments with a recognized kungfu alias replaced by its canonical name.
        """
        params = [
            parameter
            for parameter in inspect.signature(handler).parameters.values()
            if parameter.name not in {"self", "event"}
        ]
        kungfu_index = next(
            (index for index, parameter in enumerate(params) if parameter.name == "kungfu"),
            None,
        )
        if kungfu_index is None or kungfu_index >= len(args):
            return args

        prepared = list(args)
        prepared[kungfu_index] = self.kungfu_alias.resolve_kungfu(
            prepared[kungfu_index]
        )
        return prepared


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


    @filter.event_message_type(
        filter.EventMessageType.ALL,
        priority=maxsize - 10,
    )
    async def on_all_message(self, event: AstrMessageEvent):
        """解析所有消息"""
        if not self.command_map:
            logger.debug("插件尚未初始化完成，忽略消息")
            return
        
        command = self.resolve_command(event)
        if not command:
            logger.debug("未触发指令，忽略消息")
            return

        cmd, args, handler = command

        # 一旦确认是本插件指令，立即阻止后续插件和默认 LLM 继续处理。
        event.stop_event()
        event.should_call_llm(True)

        if not self.session_control.is_allowed(event.unified_msg_origin):
            logger.info(
                f"会话控制已拦截插件指令：command={cmd}, "
                f"session={event.unified_msg_origin}"
            )
            return

        try:
            args = await self._prepare_server_args(handler, event, args)
            args = self._prepare_kungfu_args(handler, args)
            ret = await self._call_with_auto_args(handler, event, args)
            if ret is not None:
                yield ret
        except Exception as e:
            logger.exception(f"指令执行失败: {cmd}, error={e}")
            yield event.plain_result("参数错误或执行失败")

    async def bind_server(
        self,
        event: AstrMessageEvent,
        server_name: str = "",
    ):
        """查看或设置当前会话绑定区服。"""
        session_id = event.unified_msg_origin
        if not server_name.strip():
            bound_server = await self.server_binding.get_binding(session_id)
            text = (
                f"当前会话绑定区服：{bound_server}"
                if bound_server
                else "当前会话尚未绑定区服。\n用法：绑定区服 区服名"
            )
        else:
            server = self.server_binding.resolve_server(server_name)
            await self.server_binding.set_binding(session_id, server)
            text = f"当前会话已绑定区服：{server}"
        await event.send(event.plain_result(text))

    async def unbind_server(self, event: AstrMessageEvent):
        """解除当前会话的区服绑定。"""
        await self.server_binding.delete_binding(event.unified_msg_origin)
        await event.send(event.plain_result("当前会话已解除区服绑定。"))
