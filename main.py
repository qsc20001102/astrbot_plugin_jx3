import inspect
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api import AstrBotConfig

from .core.sqlite import AsyncSQLiteDB
from .core.jx3_data import JX3Service
from .core.async_task import AsyncTask
from .core.bilei_data import BiLeidata
from .core.message import MessageBuilder
from .core.fun_basic import load_as_base64

@register("astrbot_plugin_jx3", 
          "fxdyz", 
          "通过调用剑网三API接口获取游戏数据，处理发送。", 
          "1.1.1",
          "https://github.com/qsc20001102/astrbot_plugin_jx3api"
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

        # 默认服务器
        self.server = self.conf.get("server","梦江南")
        logger.info(f"配置加载默认服务器：{self.server}")

        # 获取数据文件路径
        self.get_data_path()
        # 加载图片base64编码
        self.load_local_base64()
        # 构造所有类
        self.create_all()


        # 声明指令集
        self.command_map = {}

        logger.info("jx3api插件初始化完成")


    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""     
        try:
            # 数据库初始化
            await self.init_bilei_data()
            await self.init_tuishong_data()

            # 连接插件数据
            await self.plugin_sql_db.connect()

            # 开启后台推送
            await self.jx3at.init_tasks()

        except Exception as e:
            if self.jx3at is not None:
                await self.jx3at.destroy()
            logger.exception("功能模块初始化失败")
            raise

        # 指令集
        self.ini_command_map()

        logger.info("jx3api 异步插件初始化完成")


    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        
        if self.jx3at:
            await self.jx3at.destroy()

        if self.jx3api:
            await self.jx3api.close()
            
        if self.local_sql_db:
            await self.local_sql_db.close()
            
        if self.plugin_sql_db:
            await self.plugin_sql_db.close()
            
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
        # SQLite插件路径
        self.plugin_data_path = self.plugin_data_dir /"plugin_data.db"
        # API配置文件路径
        self.api_data_path = self.plugin_data_dir / "api_config.json"
        # 图片文件路径
        self.plugin_temp_img = self.plugin_temp_dir / "img"
        self.plugin_temp_sect = self.plugin_temp_dir / "sect"
        self.plugin_temp_serendipity = self.plugin_temp_dir / "serendipity"

        # 数据路径打印
        logger.debug(f"本地数据路径: {self.local_data_path}")
        logger.debug(f"插件数据路径: {self.plugin_data_path}")
        logger.debug(f"API配置文件路径: {self.api_data_path}")
        logger.debug(f"图片文件路径: {self.plugin_temp_img}")
        logger.debug(f"图片文件路径: {self.plugin_temp_sect}")
        logger.debug(f"图片文件路径: {self.plugin_temp_serendipity}")


    def load_local_base64(self):
        """加载图片文件的base64编码"""
        img = load_as_base64(str(self.plugin_temp_img))
        sect = load_as_base64(str(self.plugin_temp_sect))
        serendipity = load_as_base64(str(self.plugin_temp_serendipity))
        self.icons =  {
            "img": img,
            "sect": sect,
            "serendipity": serendipity
        }        
        logger.debug(f"图片base64编码加载完成: {self.icons}")


    def create_all(self):
        """构造所有类"""
        # 数据库实例化
        self.local_sql_db = AsyncSQLiteDB(str(self.local_data_path))
        self.plugin_sql_db = AsyncSQLiteDB(str(self.plugin_data_path))

        # 剑网三功能实例化
        self.bilei = BiLeidata(self.local_sql_db)
        self.jx3api = JX3Service(str(self.api_data_path), self.conf, self.plugin_sql_db)
        self.jx3at = AsyncTask(self.context, self.conf, self.jx3api, self.local_sql_db)
        self.jx3cmd = MessageBuilder(self.server, self.jx3api, self.bilei, self.jx3at, self.icons)


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
    

    async def init_tuishong_data(self):
        """初始化推送数据表"""
        # 创建tuishong表
        await self.local_sql_db.execute("""
        CREATE TABLE IF NOT EXISTS tuishong (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            kfts INTEGER DEFAULT 1,
            xwts INTEGER DEFAULT 0,
            smts INTEGER DEFAULT 0,
            ctts INTEGER DEFAULT 0
        )
        """)
        await self.local_sql_db.execute("""
        INSERT OR IGNORE INTO tuishong (id)
        VALUES (1)
        """)        


    def ini_command_map(self):
        """初始化指令集"""
        self.command_map = {
            "功能": self.jx3cmd.jx3_helps,
            "日常": self.jx3cmd.jx3_richang,
            "日常预测": self.jx3cmd.jx3_richangyuche,
            "名望": self.jx3cmd.jx3_xingxiashijian,
            "开服": self.jx3cmd.jx3_kaifu,
            "全服状态": self.jx3cmd.jx3_zhuangtai,
            "骚话": self.jx3cmd.jx3_shaohua,
            "技改": self.jx3cmd.jx3_jigai,
            "公告": self.jx3cmd.jx3_xinwen,
            "科举": self.jx3cmd.jx3_keju,
            "花价": self.jx3cmd.jx3_huajia,
            "装饰": self.jx3cmd.jx3_zhuangshi,
            "器物": self.jx3cmd.jx3_qiwu,
            "沙盘": self.jx3cmd.jx3_shapan,
            "统计": self.jx3cmd.jx3_qufuqiyu,
            "攻略": self.jx3cmd.jx3_qiyugonglue,
            "宏": self.jx3cmd.jx3_hong,
            "配装": self.jx3cmd.jx3_peizhuang,
            "金价": self.jx3cmd.jx3_jinjia,
            "物价": self.jx3cmd.jx3_wujia,
            "交易行": self.jx3cmd.jx3_jiaoyihang,
            "名片": self.jx3cmd.jx3_jueshemingpian,
            "随机名片": self.jx3cmd.jx3_shuijimingpian,
            "烟花": self.jx3cmd.jx3_yanhuachaxun,
            "的卢": self.jx3cmd.jx3_dilujilu,
            "招募": self.jx3cmd.jx3_tuanduizhaomu,
            "战绩": self.jx3cmd.jx3_zhanji,
            "奇遇": self.jx3cmd.jx3_qiyu,
            "拍卖": self.jx3cmd.jx3_zhengyingpaimai,
            "扶摇九天": self.jx3cmd.jx3_fuyaojjiutian,
            "刷马": self.jx3cmd.jx3_shuma,
            "骗子": self.jx3cmd.jx3_pianzhi,
            "八卦": self.jx3cmd.jx3_bagua,
            "开服推送": self.jx3cmd.jx3_kaifhujiank,
            "新闻推送": self.jx3cmd.jx3_xinwenzhixun,
            "刷马推送": self.jx3cmd.jx3_shuamamsg,
            "赤兔推送": self.jx3cmd.jx3_chitusg,
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
            prefix = self.prefix.get("text")
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
        
        # 获取消息
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







