"""
LCU连接模块 - 从本地LOL客户端读取数据
通过psutil查找进程命令行获取LCU的端口和认证令牌
支持国服和外服，自动重试和多种发现策略
"""
import os
import requests
import logging
import urllib3
import time

logger = logging.getLogger(__name__)

# 禁用InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_lcu_port = None
_lcu_token = None
_lcu_connected = False
_lcu_base_url = None
_last_connect_attempt = 0
_connect_retry_interval = 5  # 最小重试间隔（秒）


def _find_lcu_process():
    """
    通过psutil查找LOL客户端进程，获取端口和token
    支持国服和外服
    返回: {"port": str, "token": str} 或 None
    """
    try:
        import psutil
    except ImportError:
        logger.warning("psutil not installed, falling back to wmic")
        return _find_lcu_wmic()

    # 进程名优先级：LeagueClientUx.exe > LeagueClient.exe
    target_processes = ['LeagueClientUx.exe', 'LeagueClient.exe']

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            pname = proc.info['name'] or ''
            if pname in target_processes:
                cmdline = proc.info['cmdline'] or []
                cmdline_str = ' '.join(cmdline)

                port = None
                token = None

                # 解析 --app-port
                for i, arg in enumerate(cmdline):
                    if '--app-port' in arg:
                        if '=' in arg:
                            port = arg.split('=', 1)[1].strip().strip('"')
                        elif i + 1 < len(cmdline):
                            port = cmdline[i + 1].strip().strip('"')
                        break

                # 解析 --remoting-auth-token
                for i, arg in enumerate(cmdline):
                    if '--remoting-auth-token' in arg:
                        if '=' in arg:
                            token = arg.split('=', 1)[1].strip().strip('"')
                        elif i + 1 < len(cmdline):
                            token = cmdline[i + 1].strip().strip('"')
                        break

                if port and token:
                    logger.info(f"Found LCU: {pname} PID={proc.info['pid']} port={port}")
                    return {'port': port, 'token': token}

        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
            continue

    return None


def _find_lcu_wmic():
    """备用方法：通过wmic查找进程"""
    import subprocess
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where', 'name="LeagueClientUx.exe"', 'get', 'commandline'],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout

        if '--remoting-auth-token' in output:
            for line in output.split('\n'):
                if '--remoting-auth-token' in line:
                    # 解析token
                    idx = line.find('--remoting-auth-token=')
                    if idx == -1:
                        continue
                    token_start = idx + len('--remoting-auth-token=')
                    token_end = line.find(' ', token_start)
                    if token_end == -1:
                        token_end = len(line)
                    token = line[token_start:token_end].strip('"').strip()

                    # 解析port
                    idx2 = line.find('--app-port=')
                    if idx2 == -1:
                        continue
                    port_start = idx2 + len('--app-port=')
                    port_end = line.find(' ', port_start)
                    if port_end == -1:
                        port_end = len(line)
                    port = line[port_start:port_end].strip('"').strip()

                    if port and token:
                        return {'port': port, 'token': token}
    except Exception as e:
        logger.debug(f"wmic method failed: {e}")
    return None


def _find_lockfile():
    """通过lockfile查找LCU连接信息（在所有可能路径中搜索）"""
    for base_dir in _get_lockfile_search_dirs():
        path = os.path.join(base_dir, 'lockfile')
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().strip()
                # lockfile格式: LeagueClient:PID:PORT:TOKEN:PROTOCOL
                parts = content.split(':')
                if len(parts) >= 4:
                    port = parts[2]
                    token = parts[3]
                    if port and token and port.isdigit():
                        logger.info(f"Found LCU via lockfile: {path}")
                        return {'port': port, 'token': token}
            except Exception as e:
                logger.debug(f"Failed to read lockfile {path}: {e}")
    return None


def find_lcu():
    """
    查找LCU进程，获取端口和认证令牌
    自动尝试多种策略：缓存连接 -> psutil进程扫描 -> lockfile -> 端口扫描
    返回: {"success": bool, "port": str, "token": str, "method": str}
    """
    global _lcu_port, _lcu_token, _lcu_connected, _last_connect_attempt

    now = time.time()
    if now - _last_connect_attempt < _connect_retry_interval:
        if _lcu_connected:
            return {"success": True, "port": _lcu_port, "token": _lcu_token, "method": "cached"}
    _last_connect_attempt = now

    # 策略1: 测试缓存连接
    if _lcu_connected and _lcu_port and _lcu_token:
        if _test_connection(_lcu_port, _lcu_token):
            return {"success": True, "port": _lcu_port, "token": _lcu_token, "method": "cached"}
        _lcu_connected = False
        _lcu_port = None
        _lcu_token = None

    # 策略2: psutil 进程扫描
    result = _find_lcu_process()
    if result and _test_connection(result['port'], result['token']):
        _lcu_port = result['port']
        _lcu_token = result['token']
        _lcu_connected = True
        logger.info(f"LCU connected via psutil: port={_lcu_port}")
        return {"success": True, "port": _lcu_port, "token": _lcu_token, "method": "psutil"}

    # 策略3: lockfile 扫描（多路径）
    result = _find_lockfile()
    if result and _test_connection(result['port'], result['token']):
        _lcu_port = result['port']
        _lcu_token = result['token']
        _lcu_connected = True
        logger.info(f"LCU connected via lockfile: port={_lcu_port}")
        return {"success": True, "port": _lcu_port, "token": _lcu_token, "method": "lockfile"}

    # 策略4: 端口范围扫描（国服常用端口范围）
    result = _scan_lcu_ports()
    if result and _test_connection(result['port'], result['token']):
        _lcu_port = result['port']
        _lcu_token = result['token']
        _lcu_connected = True
        logger.info(f"LCU connected via port scan: port={_lcu_port}")
        return {"success": True, "port": _lcu_port, "token": _lcu_token, "method": "port_scan"}

    return {"success": False, "error": "未找到LOL客户端。请确认：\n1. 英雄联盟客户端已启动并登录\n2. 客户端正在运行中（不是后台）\n3. 尝试重启客户端后重试"}


def _test_connection(port, token):
    """快速测试LCU连接是否可用"""
    try:
        resp = requests.get(
            f"https://127.0.0.1:{port}/lol-summoner/v1/current-summoner",
            auth=("riot", token),
            timeout=3,
            verify=False
        )
        return resp.status_code == 200
    except Exception:
        return False


def _scan_lcu_ports():
    """扫描常用LCU端口范围（国服通常在 10000-60000 随机）"""
    # 先尝试从lockfile目录找到端口范围
    import glob as _glob
    lockfile_dirs = _get_lockfile_search_dirs()
    for base in lockfile_dirs:
        for pattern in [os.path.join(base, 'lockfile'), os.path.join(base, '..', 'lockfile')]:
            try:
                path = os.path.normpath(pattern)
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        content = f.read().strip()
                    parts = content.split(':')
                    if len(parts) >= 4:
                        port = parts[2]
                        token = parts[3]
                        if port and token:
                            return {'port': port, 'token': token}
            except Exception:
                continue
    return None


def _get_lockfile_search_dirs():
    """获取所有可能的lockfile搜索目录"""
    dirs = []
    # 用户AppData
    for sub in ['Local', 'Roaming', 'LocalLow']:
        appdata = os.path.join(os.path.expanduser('~'), 'AppData', sub)
        dirs.append(os.path.join(appdata, 'Riot Games', 'League of Legends'))
        dirs.append(os.path.join(appdata, 'League of Legends'))
    # ProgramData
    dirs.append(os.path.join(os.environ.get('ProgramData', 'C:\\ProgramData'), 'Riot Games', 'League of Legends'))
    # 安装目录
    for drive in ['C:', 'D:', 'E:', 'F:', 'G:']:
        for folder in [
            r'Riot Games\League of Legends',
            r'Program Files\Riot Games\League of Legends',
            r'Program Files (x86)\Riot Games\League of Legends',
            r'Games\League of Legends',
            r'腾讯游戏\英雄联盟',
            r'Tencent Games\League of Legends',
            r'WeGameApps\英雄联盟',
        ]:
            dirs.append(os.path.join(drive + '\\', folder))
    return dirs


def is_connected():
    """检查LCU是否已连接"""
    return _lcu_connected


def lcu_get(endpoint, params=None):
    """
    通过LCU API发送GET请求
    endpoint: 如 /lol-summoner/v1/current-summoner
    """
    global _lcu_connected, _lcu_port, _lcu_token
    if not _lcu_connected:
        result = find_lcu()
        if not result.get("success"):
            return result

    url = f"https://127.0.0.1:{_lcu_port}{endpoint}"
    auth = ("riot", _lcu_token)

    try:
        resp = requests.get(url, auth=auth, params=params, timeout=10, verify=False)
        if resp.status_code == 200:
            return {"success": True, "data": resp.json()}
        else:
            logger.warning(f"LCU GET {endpoint} -> {resp.status_code}: {resp.text[:200]}")
            error_detail = ""
            try:
                err_json = resp.json()
                error_detail = err_json.get("message", err_json.get("errorCode", ""))
            except Exception:
                error_detail = resp.text[:200]
            
            error_msg = f"LCU API返回错误: {resp.status_code}"
            if error_detail:
                error_msg += f" - {error_detail}"
            
            return {
                "success": False,
                "error": error_msg,
                "status": resp.status_code,
            }
    except requests.exceptions.ConnectionError:
        _lcu_connected = False
        logger.error(f"LCU连接断开: {endpoint}")
        return {"success": False, "error": "无法连接LOL客户端，请确认客户端正在运行"}
    except requests.exceptions.Timeout:
        logger.warning(f"LCU请求超时: {endpoint}")
        return {"success": False, "error": "请求超时，客户端可能无响应"}
    except Exception as e:
        logger.error(f"LCU请求异常: {e}")
        return {"success": False, "error": str(e)}


def lcu_post(endpoint, data=None, json_data=None):
    """通过LCU API发送POST请求"""
    global _lcu_connected, _lcu_port, _lcu_token
    if not _lcu_connected:
        result = find_lcu()
        if not result.get("success"):
            return result

    url = f"https://127.0.0.1:{_lcu_port}{endpoint}"
    auth = ("riot", _lcu_token)

    try:
        resp = requests.post(url, auth=auth, data=data, json=json_data, timeout=10, verify=False)
        return {"success": resp.status_code in [200, 201, 204], "data": resp.json() if resp.content else {}, "status": resp.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_current_summoner():
    """获取当前登录的召唤师信息，支持多种端点"""
    # 尝试多个可能的端点（不同版本客户端可能路径不同）
    endpoints = [
        "/lol-summoner/v1/current-summoner",
        "/lol-summoner/v2/current-summoner",
    ]
    
    last_error = None
    for endpoint in endpoints:
        result = lcu_get(endpoint)
        if result.get("success"):
            data = result["data"]
            # 国服客户端可能displayName为空，尝试多个字段
            name = data.get("displayName", "") or data.get("internalName", "") or data.get("name", "")
            # 如果名字仍为空，尝试从 /lol-chat/v1/me 获取
            if not name:
                chat_result = lcu_get("/lol-chat/v1/me")
                if chat_result.get("success"):
                    chat_data = chat_result["data"]
                    name = chat_data.get("displayName", "") or chat_data.get("gameName", "") or chat_data.get("name", "")
            return {
                "success": True,
                "summoner_id": data.get("summonerId", 0),
                "puuid": data.get("puuid", ""),
                "name": name,
                "level": data.get("summonerLevel", 0),
                "profile_icon_id": data.get("profileIconId", 0),
            }
        last_error = result
    
    # 所有端点都失败，返回详细错误
    if last_error:
        error_msg = last_error.get("error", "未知错误")
        status = last_error.get("status", 0)
        if status == 401:
            return {"success": False, "error": "认证失败，请重新启动客户端"}
        elif status == 404:
            return {"success": False, "error": "客户端API端点不可用，可能未登录"}
        elif status == 403:
            return {"success": False, "error": "权限不足，请以管理员身份运行"}
        return last_error
    return {"success": False, "error": "无法读取召唤师信息"}


def get_current_rank(puuid):
    """获取当前召唤师的排位信息"""
    # 尝试多个端点
    endpoints = [
        f"/lol-ranked/v1/ranked-stats/{puuid}",
        f"/lol-ranked/v2/ranked-stats/{puuid}",
    ]
    
    for endpoint in endpoints:
        result = lcu_get(endpoint)
        if result.get("success"):
            return {"success": True, "data": result["data"]}
    
    return {"success": False, "error": "无法获取排位信息"}


def get_game_session():
    """获取当前游戏会话状态"""
    result = lcu_get("/lol-gameflow/v1/session")
    return result


def get_lcu_status():
    """获取LCU连接状态（含诊断信息）"""
    status = {
        "connected": _lcu_connected,
        "port": _lcu_port,
        "has_token": _lcu_token is not None,
        "last_attempt": _last_connect_attempt,
    }
    if _lcu_connected and _lcu_port:
        status["health"] = "ok" if _test_connection(_lcu_port, _lcu_token) else "stale"
    return status


def force_reconnect():
    """强制重新扫描LCU连接（清除缓存状态）"""
    global _lcu_connected, _lcu_port, _lcu_token, _last_connect_attempt
    _lcu_connected = False
    _lcu_port = None
    _lcu_token = None
    _last_connect_attempt = 0
    logger.info("Force reconnecting LCU...")
    return find_lcu()
