
# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false

from datetime import datetime
from typing import Dict, Any, Optional, List, Union

from astrbot.api import logger
from astrbot.api import AstrBotConfig

from .request import APIClient
from .sqlite import AsyncSQLiteDB
from .fun_basic import load_template,gold_to_string,week_to_num,compare_date_str

class JX3Service:
    def __init__(self, api_config, config:AstrBotConfig, sqlite:AsyncSQLiteDB):
        self._api = APIClient()
        # 引用API配置文件
        self._api_config = api_config
        # 引用插件配置文件
        self._config = config
        # 引用sqlite
        self._sql_db = sqlite

        # 获取配置中的 Token
        self.token = self._config.get("jx3api_token", "")
        if  self.token == "":
            logger.info("获取配置token失败，请正确填写token,否则部分功能无法正常使用")
        else:
            logger.debug(f"获取配置token成功。{self.token}")
        # 获取配置中的 ticket
        self.ticket = self._config.get("jx3api_ticket", "")
        if  self.ticket == "":
            logger.info("获取配置ticket失败，请正确填写ticket,否则部分功能无法正常使用")
        else:
            logger.debug(f"获取配置ticket成功。{self.ticket}")
        

    async def close(self):
        """释放底层 APIClient 资源"""
        if self._api:
            await self._api.close()
            self._api = None


    def _init_return_data(self) -> Dict[str, Any]:
            """初始化标准的返回数据结构"""
            return {
                "code": 0,
                "msg": "功能函数未执行",
                "data": {},
                "temp": ""
            }
    

    async def _base_request(
        self, 
        config_key: str, 
        method: str, 
        params: Optional[Dict[str, Any]] = None, 
        out_key: Optional[str] = "data"
    ) -> Optional[Any]:
        """
        基础请求封装，处理配置获取和API调用。
        
        :param config_key: 配置字典中对应 API 的键名。
        :param method: HTTP方法 ('GET' 或 'POST')。
        :param params: 请求参数或 Body 数据。
        :param out_key: 响应数据中需要提取的字段。
        :return: 成功时返回提取后的数据，失败时返回 None。
        """
        try:
            api_config = self._api_config.get(config_key)
            if not api_config:
                logger.error(f"配置文件中未找到 key: {config_key}")
                return None
            
            # 复制 params，避免修改原始配置模板
            request_params = api_config.get("params", {}).copy()
            if params:
                request_params.update(params)

            url = api_config.get("url", "")
            if not url:
                logger.error(f"API配置缺少 URL: {config_key}")
                return None
                
            if method.upper() == 'POST':
                data = await self._api.post(url, data=request_params, out_key=out_key)
            else: # 默认为 GET
                data = await self._api.get(url, params=request_params, out_key=out_key)
            
            if not data:
                logger.warning(f"获取接口信息失败或返回空数据: {config_key}")
            
            return data
            
        except Exception as e:
            logger.error(f"基础请求调用出错 ({config_key}): {e}")
            return None


    # --- 业务功能函数 ---
    async def helps(self) -> Dict[str, Any]:
        """帮助"""
        return_data = self._init_return_data()
        
        # 加载模板
        try:
            return_data["temp"] = await load_template("helps.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
            
        return_data["code"] = 200
   
        return return_data


    async def richang(self,server: str, num: int = 0) -> Dict[str, Any]:
        """日常活动"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = {"server": server, "num": num}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_richang", "GET", params=params
        )
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
    
        # 3. 处理返回数据
        try:
            # 格式化字符串，利用字典的 get 方法提供默认值
            result_msg = (
                f"{server}\n{data.get('date', '未知日期')}-星期{data.get('week', '未知')}\n"
                f"大战：{data.get('war', '无')}\n"
                f"战场：{data.get('battle', '无')}\n"
                f"阵营：{data.get('orecar', '无')}\n"
                f"宗门：{data.get('school', '无')}\n"
                f"驰援：{data.get('rescue', '无')}\n"
                f"画像：{data.get('draw', '无')}\n\n"
            )
            
            # 安全地处理列表索引
            luck = data.get('luck', [])
            luck_msg = f"【宠物福缘】\n{', '.join(luck)}\n"
            card = data.get('card', [])
            card_msg = f"【家园声望·加倍道具】\n{', '.join(card)}\n"
            team = data.get('team', [None, None, None])
            team_msg = f"【武林通鉴·公共任务】\n{team[0] or '无'}\n【武林通鉴·团队秘境】\n{team[2] or '无'}\n"

            return_data["data"] = result_msg + luck_msg + card_msg + team_msg
            return_data["code"] = 200
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        return_data["code"] = 200

        return return_data
    
    async def richangyuche(self) -> Dict[str, Any]:
        """日常预测"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = { "num": 30}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_richangyuche", "GET", params=params
        )
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
    
        # 3. 处理返回数据
        try:
            items = []
            num_richang  = week_to_num(data["data"][0]["week"])
            # 空白数据
            for _ in range(num_richang):
                items.append({
                    "en": False,
                    "compare": "",
                    "date": "",
                    "war": "",
                    "battle": ""
                })

            # 真实数据
            for m in data["data"]:
                items.append({
                    "en": True,
                    "compare": compare_date_str(m.get("date", "")),
                    "date": m.get("date", ""),
                    "war": m.get("war", ""),
                    "battle": m.get("battle", "")
                })

            return_data["data"]["items"] = items
            return_data["data"]["today"] = data["today"]
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        # 加载模板
        try:
            return_data["temp"] = await load_template("richangyuche.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data

        return_data["code"] = 200

        return return_data
    

    async def xingxiashijian(self,name: str) -> Dict[str, Any]:
        """行侠事件"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = { "name": name}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_xingxiashijian", "GET", params=params
        )
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
    
        # 3. 处理返回数据
        try:
            return_data["data"]["items"] = data
            return_data["data"]["name"] = name
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
            
        # 加载模板
        try:
            return_data["temp"] = await load_template("xingxiashijian.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data

        return_data["code"] = 200

        return return_data


    async def keju(self,subject: str, limit: int) -> Dict[str, Any]:
        """科举"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = {"subject": subject, "limit": limit}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_keju", "GET", params=params
        )
        if not data:
            return_data["msg"] = "未查询到相关题目"
            return return_data
    
        # 3. 处理返回数据
        try:
            # 格式化字符串，利用字典的 get 方法提供默认值
            result_msg = ""
            for m in data:
                result_msg += f"{m['id']}.{m['question']}\n"
                result_msg += f"答案：{m['answer']}\n\n"

            return_data["data"] = result_msg
            
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        return_data["code"] = 200

        return return_data


    async def huajia(self,server: str, name: str, map: str) -> Dict[str, Any]:
        """花价"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = {"server": server, "name": name,  "map": map}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_huajia", "GET", params=params
        )
        if not data:
            return_data["msg"] = "未查询到相关内容"
            return return_data
    
        # 3. 处理返回数据
        try:
            return_data["data"]["data"] = data
            return_data["data"]["server"] = server
            
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data

        # 加载模板
        try:
            return_data["temp"] = await load_template("huajia.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200

        return return_data


    async def zhuangshi(self,name: str) -> Dict[str, Any]:
        """花价"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = { "name": name}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_zhuangshi", "GET", params=params
        )
        if not data:
            return_data["msg"] = "未查询到相关内容"
            return return_data
    
        # 3. 处理返回数据
        try:
            return_data["data"]["data"] = data
           
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
    
        # 加载模板
        try:
            return_data["temp"] = await load_template("zhuangshi.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200

        return return_data


    async def qiwu(self,name: str) -> Dict[str, Any]:
        """器物"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = { "name": name}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_qiwu", "GET", params=params
        )
        if not data:
            return_data["msg"] = "未查询到相关内容"
            return return_data
    
        # 3. 处理返回数据
        try:
            return_data["data"]["data"] = data
            return_data["data"]["name"] = name
            
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        # 加载模板
        try:
            return_data["temp"] = await load_template("qiwu.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200

        return return_data


    async def shapan(self, server: str ) -> Dict[str, Any]:
        """区服沙盘"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"serverName": server}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "aijx3_shapan", "POST", params=params
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        # 3. 处理返回数据 (直接提取图片 URL)
        pic_url = data.get("picUrl")
        if pic_url:
            return_data["data"] = pic_url
        else:
            return_data["msg"] = "接口未返回图片URL"
            return return_data
        
        return_data["code"] = 200    

        return return_data
    

    async def kaifu(self, server: str) -> Dict[str, Any]:
        """开服状态查询"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Union[int, str]]] = await self._base_request(
            "jx3_kaifu", "GET", params=params
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        # 3. 处理返回数据
        try:
            status = data.get("status", 0)
            timestamp = data.get("time", 0)
            
            status_time = datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
            
            if status == 1:
                status_str = f"{server}服务器已开服，快冲，快冲！\n开服时间：{status_time}"
                status_bool = True
            else:
                status_str = f"{server}服务器当前维护中，等会再来吧！\n维护时间：{status_time}"
                status_bool = False

            return_data["status"] = status_bool
            return_data["data"] = status_str
            
        except Exception as e:
            logger.error(f"kaifu 数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        return_data["code"] = 200    

        return return_data


    async def shaohua(self) -> Dict[str, Any]:
        """骚话"""
        return_data = self._init_return_data()
        
        # 因为没有参数，所以 params=None
        data: Optional[Dict[str, Any]] = await self._base_request("jx3_shaohua", "GET") 
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        text = data.get("text")
        if text:
            return_data["data"] = text
        else:
            return_data["msg"] = "接口未返回文本"
            return return_data

        return_data["code"] = 200  

        return return_data
    

    async def zhuangtai(self) -> Dict[str, Any]:
        """区服状态"""
        return_data = self._init_return_data()
        
        
        data: Optional[Dict[str, Any]] = await self._base_request("jx3_zhuangtai", "GET") 
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
        # 处理返回数据
        try:
            server_wj = []
            server_dx = []
            server_sx = []

            for itme in data:
                if itme['zone'] == "无界区":
                    server_wj.append(itme)
                elif itme['zone'] == "电信区":
                    server_dx.append(itme)
                elif itme['zone'] == "双线区":
                    server_sx.append(itme)

            return_data["data"]["server_wj"] = server_wj
            return_data["data"]["server_dx"] = server_dx
            return_data["data"]["server_sx"] = server_sx
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
        # 加载模板
        try:
            return_data["temp"] = await load_template("qufuzhuangtai.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200
            
        return return_data


    async def jigai(self) -> Dict[str, Any]:
        """技改记录"""
        return_data = self._init_return_data()
        
        # 提取字段可能返回列表
        data: Optional[List[Dict[str, Any]]] = await self._base_request("jx3_jigai", "GET")
        
        if not data or not isinstance(data, list):
            return_data["msg"] = "获取接口信息失败或数据格式错误"
            return return_data
        
        try:
            result_msg = "剑网三最近技改\n"
            # 仅展示前1条，避免消息过长
            for i, item in enumerate(data[:1], 1): 
                result_msg += f"{i}. {item.get('title', '无标题')}\n"
                result_msg += f"时间：{item.get('time', '未知时间')}\n"
                result_msg += f"链接：{item.get('url', '无链接')}\n\n"
                
            return_data["data"] = result_msg
            
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        return_data["code"] = 200

        return return_data
    

    async def xinwen(self, num:int) -> Dict[str, Any]:
        """新闻资讯"""
        return_data = self._init_return_data()

        params = {"limit": num}
        # 提取字段可能返回列表
        data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "jx3_xinweng", "GET", params=params)
        
        if not data or not isinstance(data, list):
            return_data["msg"] = "获取接口信息失败或数据格式错误"
            return return_data
        
        try:
            # 
            result = data[0]
            return_data["status"] = result.get('id')

            result_msg = "新闻资讯推送\n"
            # 仅展示前1条，避免消息过长
            for i, item in enumerate(data[:num], 1): 
                result_msg += f"{i}. {item.get('title', '无标题')}\n"
                result_msg += f"时间：{item.get('date', '未知时间')}\n"
                result_msg += f"链接：{item.get('url', '无链接')}\n"
                
            return_data["data"] = result_msg
            
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"

        return_data["code"] = 200    

        return return_data


    async def shuamamsg(self,server:str,type:str,subtype:str) -> Dict[str, Any]:
        """刷马消息"""
        return_data = self._init_return_data()

        params = {"server": server, "type": type, "subtype": subtype}
        # 提取字段可能返回列表
        data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "jx3box_shuamamsg", "GET", params=params)
        
        if not data:
            return_data["msg"] = "获取接口信息失败或数据格式错误"
            return return_data
        
        try:
            # 
            new_msg = data.get("list")[0]
            return_data["status"] = new_msg.get('id')

            result_msg = f"{server}\n"
            result_msg += f"{new_msg.get('content')}\n"
            result_msg += f"{new_msg.get('created_at')}\n"
                
            return_data["data"] = result_msg
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        return_data["code"] = 200

        return return_data


    async def jinjia(self, server: str, limit:str) -> Dict[str, Any]:
        """区服金价"""
        return_data = self._init_return_data()
        
        # 获取配置中的 Token
        token = self._config.get("jx3api_token", "")
        if  token == "":
            return_data["msg"] = "系统未配置API访问Token"
            return return_data

        params = {"server": server, "limit": limit, "token": token}
        data_list: Optional[List[Dict[str, Any]]] = await self._base_request("jx3_jinjia", "GET", params=params)
        
        if not data_list or not isinstance(data_list, list):
            return_data["msg"] = "获取接口信息失败或数据格式错误"
            return return_data
        # 加载模板
        try:
            return_data["temp"] = await load_template("jinjia.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
            
        # 准备模板渲染数据
        try:
            return_data["data"]["items"] = data_list

        except Exception as e:
            logger.error(f"模板数据准备失败: {e}")
            return_data["msg"] = "系统错误：模板渲染数据准备失败"
            return return_data
        
        return_data["code"] = 200  

        return return_data


    async def qiyu(self, adventureName: str, serverName: str) -> Dict[str, Any]:
        """区服奇遇"""
        return_data = self._init_return_data()
        
        params = {"adventureName": adventureName, "serverName": serverName}
        data_list: Optional[List[Dict[str, Any]]] = await self._base_request("aijx3_qiyu", "POST", params=params)
        
        if not data_list or not isinstance(data_list, list):
            return_data["msg"] = "获取接口信息失败或数据格式错误"
            return return_data
            
        # 格式化时间
        try:
            for item in data_list:
                timestamp = item.get("time")
                if timestamp and isinstance(timestamp, (int, float)):
                    # 修复时间戳：原代码显示这里是毫秒级，除以 1000
                    item["time"] = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    item["time"] = "未知时间" # 确保即使 time 字段缺失也不会报错
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data     

        # 加载模板
        try:
            return_data["temp"] = await  load_template("qiyuliebiao.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
            
        # 准备模板渲染数据
        try: 
            return_data["data"] = {
                "items": data_list,
                "server": serverName,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "qiyuname": adventureName
            }
            return_data["code"] = 200
        except Exception as e:
            logger.error(f"模板数据准备失败: {e}")
            return_data["msg"] = "系统错误：模板渲染数据准备失败"
            return return_data
            
        return return_data


    async def wujia(self, Name: str, server:str) -> Dict[str, Any]:
        """物价查询"""
        return_data = self._init_return_data()
        
        # 2. 确定外观名称和 ID
        
        params_search = {"name": Name,"token": self.token, "server": server}
        search_data: Optional[Dict[str, Any]] = await self._base_request("jx3_wujia", "GET", params=params_search)

        if not search_data:
            return_data["msg"] = "未找到该外观"
            return return_data
        
        return_data["data"] = search_data
            
        # 5. 加载模板
        try:
            return_data["temp"] = await load_template("wujia.html")
            return_data["code"] = 200
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data 
            
        return return_data


    async def jiaoyihang(self, name: str , server: str) -> Dict[str, Any]:
        """区服交易行"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = {"server": server, "name": name,"token": self.token}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_jiaoyihang", "GET", params=params
        )

        if not data:
            return_data["msg"] = "未找到该物品"
            return return_data
        
        # 2. 数据处理
        result = []
        
        try:
            for item in data:
                inner_list = item.get("data", []) 
                first = inner_list[0] if inner_list else {}
                new_item = {
                    "name": item.get("name"),
                    "icon": f"https://icon.jx3box.com/icon/{item.get('icon')}.png",
                    "sever": first.get("server"),
                    "count": len(inner_list),
                    "unit_price": gold_to_string(first.get("unit_price")),
                    "created": datetime.fromtimestamp(first.get("created")).strftime("%Y-%m-%d %H:%M:%S"),
                }
                result.append(new_item)
                return_data["data"]["list"] = result
        except Exception as e:
            logger.error(f"处理交易行数据失败: {e}")
            return_data["msg"] = "处理交易行数据失败"
            return return_data

        # 5. 模板渲染
        try:
            return_data["temp"] = await load_template("jiaoyihang.html")
            return_data["code"] = 200
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data

        return return_data
    

    async def jueshemingpian(self, server: str, name:str ) -> Dict[str, Any]:
        """角色名片"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server, "name": name,"token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_jieshemingpian", "GET", params=params
        )
        
        if not data:
            return_data["msg"] = "未找到该角色"
            return return_data
            
        # 3. 处理返回数据 (直接提取图片 URL)
        return_data["data"] = data['showAvatar']
        return_data["code"] = 200
        
        return return_data
    

    async def shuijimingpian(self, force: str, body:str, server:str) -> Dict[str, Any]:
        """随机名片"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = {"server": server, "body": body, "force":force, "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_shuijimingpian", "GET", params=params
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        # 3. 处理返回数据 (直接提取图片 URL)
        return_data["data"] = data['showAvatar']
        return_data["code"] = 200
        
        return return_data


    async def yanhuachaxun(self, server: str, name:str ) -> Dict[str, Any]:
        """烟花查询"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server, "name": name,"token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_yanhuachaxun", "GET", params=params
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        # 3. 处理返回数据 
        try:            
            for item in data:
                timestamp = item.get("time")
                if timestamp and isinstance(timestamp, (int, float)):
                    # 修复时间戳：原代码显示这里是毫秒级，除以 1000
                    item["time"] = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    item["time"] = "未知时间" # 确保即使 time 字段缺失也不会报错

            return_data["data"]["list"] = data
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错" 
            return return_data    
               
        # 4. 加载模板
        try:
            return_data["temp"] = await load_template("yanhuan.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200
        
        return return_data


    async def dilujilu(self, server: str) -> Dict[str, Any]:
        """的卢记录"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server, "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_dilujilu", "GET", params=params
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data

        # 3. 处理返回数据 
        try:              
            for item in data:
                item["refresh_time"] = datetime.fromtimestamp(item["refresh_time"]).strftime("%Y-%m-%d %H:%M:%S")
                item["capture_time"] = datetime.fromtimestamp(item["capture_time"]).strftime("%Y-%m-%d %H:%M:%S")
                item["auction_time"] = datetime.fromtimestamp(item["auction_time"]).strftime("%Y-%m-%d %H:%M:%S")
                return_data["data"]["list"] = data
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错" 
            return return_data

        # 4. 加载模板
        try:
            return_data["temp"] = await load_template("dilujilu.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200
        
        return return_data
    

    async def tuanduizhaomu(self, server: str, keyword: str) -> Dict[str, Any]:
        """团队招募"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server, "keyword": keyword, "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_tuanduizhaomu", "GET", params=params
        )

        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data   
        
        # 3. 处理返回数据 
        try: 
            for item in data["data"]:
                item["createTime"] = datetime.fromtimestamp(item["createTime"]).strftime("%Y-%m-%d %H:%M:%S")
                item["number"] = f"{item['number']}/{item['maxNumber']}"
                return_data["data"]["list"] = data["data"]
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错" 
            return return_data

        # 4. 加载模板
        try:
            return_data["temp"] = await load_template("tuanduizhaomu.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200
        
        return return_data
    

    async def zhanji(self, name: str, server:str, mode:str) -> Dict[str, Any]:
        """战绩+名片"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server, "name":name, "mode":mode, "token": self.token, "ticket": self.ticket}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_zhanji", "GET", params=params
        )

        if not data:
            return_data["msg"] = "查询角色战绩失败"
            return return_data
        logger.info("战绩获取完成")

        # 角色名片获取
        datamp = await self.jueshemingpian(server,name)
        if datamp["code"] == 200:
            data["showAvatar"] = datamp['data']
            logger.info("名片获取完成")
        else:
            data["showAvatar"] = ""
            logger.info("名片获取失败")

        # 4. 加载模板
        try:
            return_data["temp"] = await load_template("zhanji.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
    
        return_data["data"] = data
        return_data["code"] = 200
        
        return return_data


    async def juesheqiyu(self, name: str, server: str) -> Dict[str, Any]:
        """角色奇遇"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server, "name": name, "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_qiyu", "GET", params=params
        )

        if not data:
            return_data["msg"] = "未找到改角色奇遇信息"
            return return_data   
        
        # 3. 处理返回数据 
        try:
            return_data["data"]["ptqy"] = []
            return_data["data"]["jsqy"] = []
            return_data["data"]["cwqy"] = []

            for item in data:
                item["time"] = datetime.fromtimestamp(item["time"]).strftime("%Y-%m-%d %H:%M:%S")
                if item["level"] == 1:
                    return_data["data"]["ptqy"].append(item)
                if item["level"] == 2:
                    return_data["data"]["jsqy"].append(item)
                if item["level"] == 3:
                    return_data["data"]["cwqy"].append(item)
        except Exception as e:
            logger.error(f"处理返回数据失败: {e}")
            return_data["msg"] = "处理返回数据失败"
            return return_data

        # 4. 加载模板
        try:
            return_data["temp"] = await load_template("juesheqiyu.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200
        
        return return_data


    async def zhengyingpaimai(self, server: str, name: str) -> Dict[str, Any]:
        """阵营拍卖"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server, "name": name, "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_zhengyingpaimai", "GET", params=params
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        # 3. 处理返回数据  
        try: 
            for item in data:
                item["time"] = datetime.fromtimestamp(item["time"]).strftime("%Y-%m-%d %H:%M:%S")
            return_data["data"]["list"] = data
        except Exception as e:
            logger.error(f"处理返回数据失败: {e}")
            return_data["msg"] = "处理返回数据失败"
            return return_data

        # 4. 加载模板
        try:
            return_data["temp"] = await load_template("zhengyingpaimai.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        
        return_data["code"] = 200
        
        return return_data
    

    async def fuyaojjiutian(self, server: str) -> Dict[str, Any]:
        """扶摇九天"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server, "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_fuyaojiutian", "GET", params=params
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        # 3. 处理返回数据
        try:
            data_new =  data[0]
            data_old =  data[1]
            result_msg = f"{server}\n"
            result_msg += f"上次[扶摇九天]开启时间：{datetime.fromtimestamp(data_old['time']).strftime('%Y-%m-%d %H:%M:%S')}\n"
            result_msg += f"本次[扶摇九天]开启时间：{datetime.fromtimestamp(data_new['time']).strftime('%Y-%m-%d %H:%M:%S')}"
            return_data["data"] = result_msg
        except Exception as e:
            logger.error(f"处理返回数据失败: {e}")
            return_data["msg"] = "处理返回数据失败"
            return return_data    
        
        return_data["code"] = 200
        
        return return_data
    

    async def shuma(self, server: str) -> Dict[str, Any]:
        """刷马"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server, "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_shuama", "GET", params=params, out_key=""
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        # 3. 处理返回数据
        try:
            _data =  data["data"]["data"]
            result_msg = f"{server}\n"
            result_msg += f"黑戈壁：\n{_data['黑戈壁'][0]}\n"
            result_msg += f"阴山大草原：\n{_data['阴山大草原'][0]}\n"
            result_msg += f"鲲鹏岛：\n{_data['鲲鹏岛'][0]}\n"
            result_msg += f"{data['data']['note']}"
            return_data["data"] = result_msg
        except Exception as e:
            logger.error(f"处理返回数据失败: {e}")
            return_data["msg"] = "处理返回数据失败"
            return return_data    
        
        return_data["code"] = 200
        
        return return_data
    

    async def pianzhi(self, uid: str) -> Dict[str, Any]:
        """骗子查询"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"uid": uid, "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_pianzhi", "GET", params=params
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        # 3. 处理返回数据
        try:
            records = data["records"]

            if not records:
                result_msg = "未找到该用户行骗记录，很棒！继续保持！"
            else:
                result_msg = ""

                for record in records:
                    result_msg += f"区服：{record['server']}  标签：{record['tieba']}\n\n"

                    for item in record["data"]:
                        result_msg += f"标题：{item['title']}\n"
                        result_msg += f"地址：{item['url']}\n"
                        result_msg += f"ID：{item['tid']}\n"
                        result_msg += f"内容：{item['text']}\n"
                        result_msg += (
                            f"时间：{datetime.fromtimestamp(item['time']).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        )

                    result_msg += "\n\n"
            return_data["data"] = result_msg
        except Exception as e:
            logger.error(f"处理返回数据失败: {e}")
            return_data["msg"] = "处理返回数据失败"
            return return_data
            
        return_data["code"] = 200
        
        return return_data
    

    async def bagua(self, type: str) -> Dict[str, Any]:
        """八卦"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"class": type, "limit": "5", "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_bagua", "GET", params=params
        )
        
        # 3. 处理返回数据
        try:
            if not data:
                result_msg = f"未找到相关 {type} 记录。\n"
                result_msg += f"可选范围：818 616 鬼网三 鬼网3 树洞 记录 教程 街拍 故事 避雷 吐槽 提问"
            else:
                result_msg = f"类型：{type} 的最新记录如下：\n\n"

                for item in data:
                    result_msg += f"{item['title']}\n"
                    result_msg += f"分区：{item['zone']}  服务器：{item['server']}\n"
                    result_msg += f"所属吧：{item['name']}\n"
                    result_msg += f"链接：https://tieba.baidu.com/p/{item['url']}\n"
                    result_msg += f"日期：{item['date']}\n\n"
            return_data["data"] = result_msg
        except Exception as e:
            logger.exception("处理返回数据失败")
            return_data["msg"] = "处理返回数据失败"
            return return_data    

        return_data["code"] = 200
        
        return return_data
    

    async def qiyugonglue(self, name: str) -> Dict[str, Any]:
        """奇遇攻略"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"name": name}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3box_qiyugonglue", "GET", params=params, out_key="list"
        )
        
        if not data:
            return_data["msg"] = "未找到该奇遇"
            return return_data
        
        # 提取dwID
        dwID = data[0]["dwID"]
        url = f"https://node.jx3box.com/serendipity/{dwID}/achievement"
        logger.debug(f"获取ID接口地址：{url}")

        # 3. 获取奇遇攻略
        # 获取achievement_id
        data1 = await self._api.get(url)
        url1 = f"https://cms.jx3box.com/api/cms/wiki/post/type/achievement/source/{data1['achievement_id']}"
        logger.debug(f"获取攻略接口地址：{url1}")
        # 获取奇遇攻略
        data2 = await self._api.get(url1, out_key="data")
        if not data2:
            return_data["msg"] = "获取攻略数据异常"
            return return_data
        
        # 4. 处理数据
        try:
            return_data["data"] = {}
            content = data2["post"]["content"]
            return_data["temp"] = content
        except Exception as e:
            logger.exception("处理返回数据失败")
            return_data["msg"] = "处理返回数据失败"
            return return_data

        return_data["code"] = 200

        return return_data
    

    async def hong1(self, name: str) -> Dict[str, Any]:
        """宏 心法"""
        return_data = self._init_return_data()
        
        # 数据库查询数据
        result = await self._sql_db.select_one(
                "kungfu",
                "name=? OR name1=? OR name2=? OR name3=? OR name4=? OR name5=?",
                (name, name, name, name, name, name)
            )

        kungfu = result.get("name",None)
        if kungfu == None:
            return_data["msg"] = "未找到该心法"
            return return_data
        
        logger.debug(f"查询到数据：{kungfu}")

        # 1. 构造请求参数
        params = {"kungfu": kungfu}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3box_hong", "GET", params=params, out_key=""
        )
        logger.debug(data)
        if not data:
            return_data["msg"] = "未找到该心法一键宏"
            return return_data
        
        # 提取ID
        pid_list = [0]
        msg = "按照热度排列\n"
        n = 1
        try:
            for m in data:
                msg += f"{n}、{m['author']}\t{m['item_version']}\n"
                pid_list.append(m["pid"])
                n += 1
            
            return_data["msg"] = msg
            return_data["data"]["list"] = pid_list
            return_data["data"]["num"] = n

        except Exception as e:
            logger.exception("处理返回数据失败")
            return_data["msg"] = "处理返回数据失败"
            return return_data
        
        return_data["code"] = 200

        return return_data
    

    async def hong2(self, pid: str) -> Dict[str, Any]:
        """宏 心法"""
        return_data = self._init_return_data()
        
        # 发起请求
        url = f"https://cms.jx3box.com/api/cms/post/{pid}"
        logger.debug(f"获取宏接口地址：{url}")
        data = await self._api.get(url, out_key="data")
        # 验证数据
        if not data:
            return_data["msg"] = "获取宏数据异常"
            return return_data
        
        # 4. 处理数据
        try:
            return_data["temp"] = data["post_content"]
            msg = ""
            for m in data["post_meta"]["data"]:
                msg += f"【宏名称】\n{m['name']}\n"
                msg += f"【使用说明】\n{m['desc']}\n"
                msg += f"【宏脚本】\n{m['macro']}\n\n"

            return_data["data"] = msg
            
        except Exception as e:
            logger.exception("处理返回数据失败")
            return_data["msg"] = "处理返回数据失败"
            return return_data
        
        return_data["code"] = 200

        return return_data
    

    async def peizhuang(self, name: str, tags: str) -> Dict[str, Any]:
        """配装"""
        return_data = self._init_return_data()
        
        # 数据库查询数据
        result = await self._sql_db.select_one(
                "kungfu",
                "name=? OR name1=? OR name2=? OR name3=? OR name4=? OR name5=?",
                (name, name, name, name, name, name)
            )

        mount = result.get("pzid",None)
        if mount == None:
            return_data["msg"] = "未找到该心法"
            return return_data
        
        logger.debug(f"查询到数据：{mount}")

        # 1. 构造请求参数
        params = {"mount": mount, "tags": tags}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3box_peizhuang", "GET", params=params
        )
        logger.debug(data)
        # 验证数据
        if not data:
            return_data["msg"] = "配装数据获取异常"
            return return_data
        
        # 3. 处理返回数据
        try:
            result_msg = f"{name}--配装\n"        
            for item in data["list"]:
                result_msg += f"【{item['zlp']}】--{item['title']}\n"
                result_msg += f"链接：https://www.jx3box.com/pz/view/{item['id']}\n\n"

            return_data["data"] = result_msg

        except Exception as e:
            logger.exception("处理返回数据失败:",e)
            return_data["msg"] = "处理返回数据失败"
            return return_data    

        return_data["code"] = 200
        
        return return_data
    
        