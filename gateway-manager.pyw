# -*- coding: utf-8 -*-
"""
OpenClaw 网关管理器 v7.0
商业级自适应网关管理工具

架构设计：
1. 端口扫描优先 - 100%可靠的实例发现
2. WSL配置读取增强 - 获取详细信息
3. 内置自动守护 - 不依赖网关内置

Author: 镜子 AI
Date: 2026-04-30
"""

import subprocess
import sys
import time
import os
import json
import threading
import socket
from datetime import datetime

VERSION = "7.0"
APP_NAME = "OpenClaw 网关管理器"
GUARD_INTERVAL = 5
MAX_RETRIES = 3
PORT_SCAN_START = 18780
PORT_SCAN_END = 18999

# ========== 只读模式开关 ==========
READ_ONLY_MODE = True  # True=只监控不操作，False=允许操作
FORBIDDEN_PATHS = ['openclaw-haixin', 'openclaw-91shenwa', '.openclaw-haixin', '.openclaw-91shenwa']

def is_safe_path(path):
    """检查路径是否涉及其他实例"""
    if not path:
        return True
    for forbidden in FORBIDDEN_PATHS:
        if forbidden in path:
            return False
    return True

def safe_wsl_cmd(cmd, operation="操作"):
    """安全的WSL命令执行（只读模式下仅显示不执行）"""
    if READ_ONLY_MODE:
        log(f"  [只读模式] 应执行: {cmd}")
        return True, "(只读模式，未实际执行)"
    return wsl_cmd(cmd)

def get_save_dir():
    """获取保存目录（默认为 D:\openclaw运行\龙虾网关管理器）"""
    default_dir = r'D:\openclaw运行\龙虾网关管理器'
    try:
        if os.path.exists(default_dir):
            return default_dir
        # 尝试创建
        os.makedirs(default_dir, exist_ok=True)
        return default_dir
    except:
        pass
    # 回退到脚本所在目录
    return os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = get_save_dir()
LOG_FILE = os.path.join(SCRIPT_DIR, 'gateway-manager.log')
BACKUP_DIR = os.path.join(SCRIPT_DIR, 'backups')

# 确保备份目录存在
os.makedirs(BACKUP_DIR, exist_ok=True)

def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except:
        pass

def show_banner():
    mode_str = "🔒 只读模式（禁止操作）" if READ_ONLY_MODE else "⚠️ 警告（允许操作）"
    banner = f"""
{'='*56}
  {APP_NAME} v{VERSION}
{'='*56}
  [模式] {mode_str}
  [只读] 只监控，不执行任何操作（start/stop/restart/restore）
  [安全] 禁止操作其他实例路径（haixin/91shenwa）
{'='*56}
    """
    print(banner)
    log(f"启动，模式: {'只读' if READ_ONLY_MODE else '可操作'}")

# ==================== 阶段1: 端口扫描（核心）====================
def get_instance_info(port):
    """尝试通过API获取实例详细信息"""
    try:
        import urllib.request
        req = urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2)
        data = json.loads(req.read().decode())
        return {
            'status': data.get('status', 'unknown'),
            'version': data.get('version', 'unknown'),
            'uptime': data.get('uptime', 0),
            'model': data.get('model', 'unknown')
        }
    except:
        return {'status': 'unknown', 'version': 'N/A', 'uptime': 0, 'model': 'N/A'}

def format_uptime(seconds):
    """格式化运行时间"""
    if seconds <= 0:
        return "N/A"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"

# ==================== 阶段1: 端口扫描（核心）====================
def get_instance_info(port):
    """尝试通过API获取实例详细信息"""
    try:
        import urllib.request
        req = urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2)
        data = json.loads(req.read().decode())
        return {
            'status': data.get('status', 'unknown'),
            'version': data.get('version', 'unknown'),
            'uptime': data.get('uptime', 0),
            'model': data.get('model', 'unknown')
        }
    except:
        return {'status': 'unknown', 'version': 'N/A', 'uptime': 0, 'model': 'N/A'}

def format_uptime(seconds):
    """格式化运行时间"""
    if seconds <= 0:
        return "N/A"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"

def scan_by_port_range():
    """策略1：端口范围扫描（最可靠）"""
    log("  [策略1] 端口范围扫描...")
    found = []
    for port in range(PORT_SCAN_START, PORT_SCAN_END + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.1)
        try:
            result = sock.connect_ex(('127.0.0.1', port))
            if result == 0:
                info = get_instance_info(port)
                found.append({'port': port, 'info': info, 'strategy': 'port-scan'})
                log(f"    ✅ 端口 {port} 开放 | {info['status']}")
        except:
            pass
        finally:
            sock.close()
    log(f"  [策略1] 完成：发现 {len(found)} 个端口")
    return found

def scan_by_process():
    """策略2：进程扫描（通过tasklist找到openclaw-gateway）"""
    log("  [策略2] Windows进程扫描...")
    found = []
    try:
        result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq openclaw-gateway.exe'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines:
                if 'openclaw-gateway' in line.lower():
                    parts = line.split()
                    if len(parts) >= 2:
                        log(f"    发现进程: {line.strip()}")
                        found.append({'process': line.strip(), 'strategy': 'process'})
    except Exception as e:
        log(f"  [策略2] 进程扫描失败: {e}")
    log(f"  [策略2] 完成：发现 {len(found)} 个进程")
    return found

def scan_wsl_processes():
    """策略3：WSL进程扫描（找到openclaw-gateway进程及端口）"""
    log("  [策略3] WSL进程扫描...")
    found = []
    
    # 查找openclaw-gateway进程
    ok, output = wsl_cmd('ps aux | grep openclaw-gateway | grep -v grep', timeout=10)
    if ok and output:
        for line in output.split('\n'):
            if line.strip():
                log(f"    进程: {line[:80]}")
                # 尝试从进程信息提取端口
                parts = line.split()
                # 简单检查，如果进程在运行但没有端口信息，后面会通过端口扫描补充
    
    # 扫描所有WSL进程可能监听的端口
    for port in range(PORT_SCAN_START, PORT_SCAN_END + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.1)
        try:
            result = sock.connect_ex(('127.0.0.1', port))
            if result == 0:
                info = get_instance_info(port)
                found.append({'port': port, 'info': info, 'strategy': 'wsl-process'})
                log(f"    WSL发现端口 {port} | {info['status']}")
        except:
            pass
        finally:
            sock.close()
    
    log(f"  [策略3] 完成：发现 {len(found)} 个端口")
    return found

def scan_ports():
    """综合端口扫描：使用多种策略确保不漏报"""
    log("=" * 60)
    log("[阶段1] 多策略端口扫描")
    log("=" * 60)
    
    open_ports = []
    port_details = {}
    strategies_used = []
    
    # 策略1：端口范围扫描（必须执行，最可靠）
    p1_results = scan_by_port_range()
    strategies_used.append(f"port-scan:{len(p1_results)}")
    for r in p1_results:
        port = r['port']
        if port not in open_ports:
            open_ports.append(port)
            port_details[port] = r['info']
    
    # 策略2：Windows进程扫描（补充）
    p2_results = scan_by_process()
    strategies_used.append(f"process:{len(p2_results)}")
    # 进程扫描主要用来确认，不额外添加端口
    
    # 策略3：WSL进程扫描（补充）
    p3_results = scan_wsl_processes()
    strategies_used.append(f"wsl-process:{len(p3_results)}")
    for r in p3_results:
        port = r['port']
        if port not in open_ports:
            open_ports.append(port)
            port_details[port] = r['info']
    
    # 按端口排序
    open_ports.sort()
    
    log(f"[阶段1] 扫描完成: {len(open_ports)} 个活跃端口")
    log(f"  策略统计: {', '.join(strategies_used)}")
    
    for port in open_ports:
        info = port_details.get(port, {'status': 'unknown', 'version': 'N/A', 'uptime': 0})
        status_icon = "✅" if info['status'] == 'live' else "⚠️"
        log(f"  {status_icon} {port} | 状态:{info['status']} | 运行:{format_uptime(info['uptime'])}")
    
    return open_ports, port_details

# ==================== 阶段2: WSL配置读取（增强）====================
def wsl_cmd(cmd, timeout=15):
    """执行WSL命令并返回输出"""
    import subprocess
    
    CREATE_NO_WINDOW = 0x08000000
    
    # 方法1: 直接wsl.exe
    try:
        result = subprocess.run(
            ['wsl', '-e', 'bash', '-c', cmd],
            capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW
        )
        if result.returncode == 0 and result.stdout and result.stdout.strip():
            return True, result.stdout.strip()
        log(f"  [WSL-M1] 失败: rc={result.returncode}, stdout={str(result.stdout)[:50]}, stderr={str(result.stderr)[:50]}")
    except Exception as e:
        log(f"  [WSL-M1] 异常: {e}")
    
    # 方法2: cmd /c wsl
    try:
        result2 = subprocess.run(
            ['cmd', '/c', 'wsl', '-e', 'bash', '-c', cmd],
            capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW
        )
        if result2.returncode == 0 and result2.stdout and result2.stdout.strip():
            return True, result2.stdout.strip()
        log(f"  [WSL-M2] 失败: rc={result2.returncode}, stdout={str(result2.stdout)[:50]}, stderr={str(result2.stderr)[:50]}")
    except Exception as e:
        log(f"  [WSL-M2] 异常: {e}")
    
    # 方法3: powershell
    try:
        result3 = subprocess.run(
            ['powershell', '-Command', 'wsl -e bash -c "' + cmd + '"'],
            capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW
        )
        if result3.returncode == 0 and result3.stdout and result3.stdout.strip():
            return True, result3.stdout.strip()
        log(f"  [WSL-M3] 失败: rc={result3.returncode}, stdout={str(result3.stdout)[:50]}, stderr={str(result3.stderr)[:50]}")
    except Exception as e:
        log(f"  [WSL-M3] 异常: {e}")
    
    return False, ""

def get_wsl_home():
    """获取WSL home目录"""
    ok, out = wsl_cmd('echo $HOME')
    if ok and out and '/' in out:
        return out
    # 如果失败，尝试备用方法
    ok2, out2 = wsl_cmd('echo ~')
    if ok2 and out2 and '/' in out2:
        return out2
    return "/home/lulu3121"  # 最后备用

def read_wsl_file(path):
    """读取WSL文件"""
    ok, out = wsl_cmd(f'cat "{path}"')
    if ok and out and not out.startswith('cat:'):
        return out
    return None

def scan_wsl_configs():
    """扫描WSL中的OpenClaw配置文件（增强版）"""
    log("=" * 60)
    log("[阶段2] WSL配置扫描")
    log("=" * 60)
    
    configs = {}
    
    # 详细日志记录扫描过程
    log(f"  开始扫描，home={get_wsl_home()}")
    
    # 先获取WSL基本信息
    home = get_wsl_home()
    if not home:
        log("  ❌ 无法获取WSL home，跳过配置扫描")
        return configs
    
    log(f"  📂 WSL home: {home}")
    
    # 策略1: find命令扫描openclaw.json
    log("  [策略A] 文件扫描...")
    search_paths = [
        f'{home}/.openclaw/openclaw.json',
        f'{home}/.openclaw-haixin/openclaw.json',
        f'{home}/.openclaw-91shenwa/openclaw.json',
    ]
    
    # 扫描所有.openclaw*目录
    log(f"  [策略A] 执行find命令: find {home} -maxdepth 4 -name openclaw.json")
    ok, output = wsl_cmd(f'find {home} -maxdepth 4 -name "openclaw.json" 2>/dev/null | head -20', timeout=15)
    
    if ok and output:
        log(f"  [策略A] find成功，找到 {len(output.split(chr(10)))} 个配置文件: {output[:200]}")
        # 批量读取所有配置文件内容（避免连续调用wsl_cmd导致失败）
        # 直接用 xargs 批量读取所有找到的配置文件
        log(f"  [策略A] 批量读取配置文件...")
        config_contents = {}
        # 处理换行符（可能包含\r）
        all_lines = output.replace('\r', '\n').split('\n')
        files = [f.strip() for f in all_lines if f.strip() and '.json' in f.lower()]
        log(f"  [策略A] 找到 {len(files)} 个文件")
        for line in files:
            line = line.strip()
            if not line:
                continue
            log(f"    📄 {line}")
            # 修复：使用find -exec（最可靠的方式）
            ok, file_content = wsl_cmd(f'find {line} -exec cat {{}} +')
            
            if ok and file_content:
                config_contents[line] = file_content
                log(f"    ✅ 成功 ({len(file_content)} bytes)")
            else:
                log(f"    ❌ 失败: ok={ok}")
                # 诊断：测试简单命令
                ok_test, out_test = wsl_cmd('echo ok')
                log(f"    [诊断] echo ok: ok={ok_test}, out={repr(out_test)}")
        
        # 解析配置文件
        for line, content in config_contents.items():
            if content:
                    try:
                        cfg = json.loads(content)
                        gw = cfg.get('gateway', {})
                        port = gw.get('port', 0)
                        name = gw.get('name', '')
                        
                        # 提取更多信息
                        models = cfg.get('models', {}).get('providers', {}).get('minimax', {}).get('models', [])
                        model_count = len(models) if models else 0
                        
                        if port:
                            configs[port] = {
                                'name': name or f'Instance-{port}',
                                'port': port,
                                'source': 'wsl',
                                'config_path': line,
                                'config_content': content,
                                'model_count': model_count,
                                'models': models[:3] if models else []
                            }
                            log(f"    ✅ {name or 'Instance-'+str(port)} (端口:{port}) | 模型:{model_count}")
                        else:
                            log(f"    ⚠️ 配置文件无端口信息，跳过")
                    except json.JSONDecodeError as e:
                        log(f"    ❌ JSON解析失败: {e}")
                    except Exception as e:
                        log(f"    ❌ 解析错误: {e}")
    else:
        log("  ⚠️ 未发现openclaw.json配置文件")
    
    # 策略2: 检查常见路径（即使find没找到也尝试读取）
    log("  [策略B] 常见路径检查...")
    for path in search_paths:
        if path in [configs.get(p, {}).get('config_path') for p in configs]:
            continue  # 已扫描过
        ok, out = wsl_cmd(f'test -f "{path}" && echo EXISTS || echo MISSING', timeout=5)
        if ok and 'EXISTS' in out:
            content = read_wsl_file(path)
            if content:
                try:
                    cfg = json.loads(content)
                    port = cfg.get('gateway', {}).get('port', 0)
                    if port and port not in configs:
                        configs[port] = {
                            'name': cfg.get('gateway', {}).get('name', f'Instance-{port}'),
                            'port': port,
                            'source': 'wsl',
                            'config_path': path,
                            'config_content': content
                        }
                        log(f"    ✅ 通过路径找到: {path}")
                except:
                    pass
    
    # 策略C: 直接检查已知的三个实例路径（确保不漏）
    log(f"  [策略C] 检查已知实例路径...")
    known_paths = [
        (18789, f'{home}/.openclaw/openclaw.json'),
        (18890, f'{home}/.openclaw-haixin/.openclaw/openclaw.json'),
        (18991, f'{home}/.openclaw-91shenwa/.openclaw/openclaw.json'),
    ]
    for port, path in known_paths:
        if port not in configs:
            log(f"    [策略C] 尝试读取: {path}")
            # 使用find -exec直接读取
            ok, out = wsl_cmd(f'find {path} -exec cat {{}} +')
            if not ok or not out:
                ok2, out2 = wsl_cmd(f'find {path} -exec cat {{}} +')
                if ok2 and out2:
                    out = out2
            if ok and out:
                content = out
                log(f"    [策略C] 读取成功，内容长度: {len(content)}")
                try:
                    cfg = json.loads(content)
                    p = cfg.get('gateway', {}).get('port', 0)
                    name = cfg.get('gateway', {}).get('name', f'Instance-{{port}}')
                    if p:
                        configs[p] = {{
                            'name': name,
                            'port': p,
                            'source': 'wsl',
                            'config_path': path,
                            'config_content': content
                        }}
                        log(f"    ✅ 策略C成功: {name} (端口:{p})")
                    else:
                        log(f"    ❌ 策略C失败: port为空")
                except json.JSONDecodeError as e:
                    log(f"    ❌ 策略C JSON解析失败: {e}")
                except Exception as e:
                    log(f"    ❌ 策略C解析错误: {e}")
            else:
                out_preview = str(out)[:50] if out else "None"
                log(f"    ❌ 策略C失败: wsl_cmd返回ok={ok}, out={out_preview}")

    log(f"[阶段2] WSL配置扫描完成: 发现 {len(configs)} 个有效配置")
    return configs

# ==================== 综合发现====================
def discover_instances(force_rescan=False):
    """综合扫描所有OpenClaw实例
    
    Args:
        force_rescan: True=强制重新扫描，False=尝试读取缓存
    """
    # 尝试加载缓存（除非强制重新扫描）
    cache_file = os.path.join(SCRIPT_DIR, 'instances_cache.json')
    
    # 永久缓存：除非force_rescan=True，否则永远读缓存
    if not force_rescan and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            instances = cached.get('instances', [])
            if instances:
                log(f"从缓存加载: {len(instances)} 个实例")
                log(f"  如需重新扫描，请点击'🔍 扫描'按钮")
                return instances
        except:
            pass
    
    open(LOG_FILE, 'w').close()
    
    log("=" * 60)
    log(f"{APP_NAME} v{VERSION} 开始扫描")
    log("=" * 60)
    
    instances = []
    
    # 阶段1: 端口扫描（获取活跃实例+状态）
    open_ports, port_details = scan_ports()
    
    # 阶段2: WSL配置扫描（获取配置详情）
    wsl_configs = scan_wsl_configs()
    
    # 合并结果
    for port in open_ports:
        info = port_details.get(port, {})
        if port in wsl_configs:
            # 有配置信息
            cfg = wsl_configs[port]
            instances.append({
                'name': cfg['name'],
                'port': port,
                'source': 'wsl',
                'config_path': cfg.get('config_path', ''),
                'config_content': cfg.get('config_content', ''),
                'status': info.get('status', 'unknown'),
                'uptime': info.get('uptime', 0),
                'uptime_str': format_uptime(info.get('uptime', 0))
            })
            log(f"  📦 {cfg['name']} ({port}) - 配置:✅ | 状态:{info['status']} | 运行:{format_uptime(info['uptime'])}")
        else:
            # 无配置，只是端口开放（可能是其他服务占用端口）
            instances.append({
                'name': f'端口-{port}',
                'port': port,
                'source': 'port-scan',
                'config_path': '',
                'config_content': '',
                'status': info.get('status', 'unknown'),
                'uptime': info.get('uptime', 0),
                'uptime_str': format_uptime(info.get('uptime', 0)),
                'warning': '无OpenClaw配置文件'
            })
            log(f"  ⚠️  端口-{port} - 开放但无配置文件（可能是其他服务）")
    
    # 统计
    configured = sum(1 for i in instances if i['source'] == 'wsl')
    scan_only = sum(1 for i in instances if i['source'] == 'port-scan')
    
    log("=" * 60)
    log(f"扫描完成: {len(instances)} 个 (OpenClaw配置:{configured} / 仅端口开放:{scan_only})")
    log("  注: '仅端口开放' 表示该端口有响应但不是OpenClaw实例")
    log("=" * 60)
    
    # 保存缓存
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                'instances': instances,
                'timestamp': time.time()
            }, f, ensure_ascii=False, indent=2)
    except:
        pass
    
    return instances

# ==================== 健康检测====================
def check_health(port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0
    except:
        return False

# ==================== 网关操作（只读模式保护）====================
def restart_gateway(inst):
    port = inst['port']
    if inst.get('source') == 'wsl':
        dir_path = inst.get('config_path', '').rsplit('/', 1)[0] if inst.get('config_path') else '~'
        if not is_safe_path(inst.get('config_path', '')):
            log(f"  [安全检查] 拒绝操作：涉及其他实例路径 {inst.get('config_path')}")
            return False
        if READ_ONLY_MODE:
            log(f"  [只读模式] 应执行: pkill -f openclaw-gateway.*{port} && cd {dir_path} && nohup openclaw gateway run...")
            return check_health(port)
        safe_wsl_cmd(f'pkill -f "openclaw-gateway.*{port}" 2>/dev/null; sleep 2')
        safe_wsl_cmd(f'cd {dir_path}; nohup openclaw gateway run --port {port} --bind loopback > {dir_path}/gateway.log 2>&1 &')
    time.sleep(3)
    return check_health(port)

def stop_gateway(inst):
    port = inst['port']
    if inst.get('source') == 'wsl':
        if not is_safe_path(inst.get('config_path', '')):
            log(f"  [安全检查] 拒绝操作：涉及其他实例路径 {inst.get('config_path')}")
            return False
        if READ_ONLY_MODE:
            log(f"  [只读模式] 应执行: pkill -f openclaw-gateway.*{port}")
            return not check_health(port)
        safe_wsl_cmd(f'pkill -f "openclaw-gateway.*{port}" 2>/dev/null')
    time.sleep(1)
    return not check_health(port)

def start_gateway(inst):
    port = inst['port']
    if inst.get('source') == 'wsl':
        dir_path = inst.get('config_path', '').rsplit('/', 1)[0] if inst.get('config_path') else '~'
        if not is_safe_path(inst.get('config_path', '')):
            log(f"  [安全检查] 拒绝操作：涉及其他实例路径 {inst.get('config_path')}")
            return False
        if READ_ONLY_MODE:
            log(f"  [只读模式] 应执行: cd {dir_path} && nohup openclaw gateway run --port {port}...")
            return check_health(port)
        safe_wsl_cmd(f'cd {dir_path}; nohup openclaw gateway run --port {port} --bind loopback > {dir_path}/gateway.log 2>&1 &')
    time.sleep(3)
    return check_health(port)

# ==================== 备份恢复====================
def backup_instance(inst):
    if not inst.get('config_content'):
        return False, "无配置内容"
    
    name_safe = inst['name'].replace(' ', '_')
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(BACKUP_DIR, f"{name_safe}_{ts}.json")
    
    data = {
        'name': inst['name'],
        'port': inst['port'],
        'source': inst.get('source', 'unknown'),
        'config_path': inst.get('config_path', ''),
        'config_content': inst.get('config_content', ''),
        'backup_time': ts
    }
    
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True, backup_file
    except Exception as e:
        return False, str(e)

def restore_instance(backup_file):
    try:
        with open(backup_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        content = data['config_content']
        path = data['config_path']
        
        if data.get('source') == 'wsl' and path:
            if not is_safe_path(path):
                log(f"  [安全检查] 拒绝恢复：涉及其他实例路径 {path}")
                return False, f"安全检查拒绝：{path}"
            if READ_ONLY_MODE:
                log(f"  [只读模式] 应执行: cp backup -> {path}")
                return True, "(只读模式，未实际恢复)"
            # 写入WSL文件
            temp = os.environ.get('TEMP', '/tmp') + '/restore_tmp.json'
            with open(temp, 'w', encoding='utf-8') as f:
                f.write(content)
            safe_wsl_cmd(f'cp "{temp}" "{path}" && rm -f "{temp}"', '恢复配置')
        
        return True, f"已恢复到 {data['backup_time']}"
    except Exception as e:
        return False, str(e)

def list_backups():
    backups = []
    if os.path.isdir(BACKUP_DIR):
        for f in os.listdir(BACKUP_DIR):
            if f.endswith('.json'):
                try:
                    with open(os.path.join(BACKUP_DIR, f), 'r', encoding='utf-8') as fp:
                        d = json.load(fp)
                        backups.append({
                            'file': f,
                            'name': d.get('name', ''),
                            'port': d.get('port', 0),
                            'time': d.get('backup_time', '')
                        })
                except:
                    pass
    return sorted(backups, key=lambda x: x['time'], reverse=True)

# ==================== GUI====================
try:
    from tkinter import *
    from tkinter import messagebox
except ImportError:
    print('需要tkinter')
    sys.exit(1)

class App:
    def __init__(self):
        self.root = Tk()
        self.root.title(f'🛡️ {APP_NAME} v{VERSION}')
        self.root.geometry('700x800')
        
        self.instances = []
        self.cards = {}
        self.guard_on = False
        self.guard_thread = None
        
        self.build_ui()
        
        # 永远从缓存加载，不自动扫描
        cache_file = os.path.join(SCRIPT_DIR, 'instances_cache.json')
        if os.path.exists(cache_file):
            self.log('📂 从缓存加载实例列表...')
            self.instances = discover_instances(force_rescan=False)
            self.refresh_ui()
            openclaw_count = len([i for i in self.instances if i.get('source') == 'wsl'])
            self.log(f'✅ 加载完成: {openclaw_count} 个OpenClaw实例 | 如需重新扫描请点击🔍扫描')
        else:
            # 没有缓存，显示空界面，等待用户手动扫描
            self.log('⚠️ 无缓存，请点击🔍扫描以发现实例')
            self.status_lbl.config(text='⚠️ 无缓存', fg='#E74C3C')
        
        self.start_guard()
    
    def show_splash(self):
        """显示启动进度窗口（带真实后台扫描）"""
        splash = Toplevel(self.root)
        splash.title('初始化中...')
        splash.geometry('400x250')
        splash.overrideredirect(True)
        splash.attributes('-topmost', True)
        
        # 居中
        splash.update_idletasks()
        x = (splash.winfo_screenwidth() // 2) - (200)
        y = (splash.winfo_screenheight() // 2) - (125)
        splash.geometry(f'400x250+{x}+{y}')
        
        # 内容
        Frame(splash, bg='#2C3E50', height=60).pack(fill=X)
        Label(splash, text=f'🛡️ {APP_NAME}', font=('Arial', 14, 'bold'), 
              fg='white', bg='#2C3E50').pack(pady=15)
        
        self.splash_label = Label(splash, text='准备初始化...', font=('Arial', 10), fg='#7F8C8D')
        self.splash_label.pack(pady=5)
        
        # 进度条
        self.splash_progress = Label(splash, text='', font=('Consolas', 9), fg='#3498DB')
        self.splash_progress.pack(pady=2)
        
        # Canvas进度条
        self.splash_canvas = Canvas(splash, width=300, height=20, bg='#ECF0F1')
        self.splash_canvas.pack(pady=10)
        self.splash_bar = self.splash_canvas.create_rectangle(5, 5, 5, 19, fill='#3498DB', outline='')
        
        # 状态标签
        self.splash_status = Label(splash, text='', font=('Consolas', 8), fg='#95A5A6', wraplength=350)
        self.splash_status.pack(pady=5)
        
        splash.update()
        
        # 在后台线程执行扫描
        def background_scan():
            import threading
            
            def update_progress(step, status, pct):
                def _update():
                    self.splash_label.config(text=step)
                    self.splash_progress.config(text=f'{pct}%')
                    self.splash_status.config(text=status)
                    bar_width = int(290 * pct / 100)
                    self.splash_canvas.coords(self.splash_bar, 5, 5, bar_width, 19)
                    splash.update()
                splash.after(0, _update)
            
            update_progress('正在加载配置...', '准备扫描环境', 10)
            time.sleep(0.2)
            
            update_progress('正在扫描端口...', '检测 18780-18999 范围内的端口', 25)
            # 执行端口扫描（这部分是阻塞的，但我们在后台线程）
            open_ports, port_details = scan_ports()
            update_progress('正在读取WSL配置...', f'发现 {len(open_ports)} 个端口，准备读取配置', 50)
            
            time.sleep(0.2)
            
            update_progress('正在读取WSL配置...', '扫描 openclaw.json 配置文件', 60)
            wsl_configs = scan_wsl_configs()
            
            update_progress('正在获取实例信息...', '合并扫描结果', 75)
            time.sleep(0.1)
            
            # 合并结果
            instances = []
            for port in open_ports:
                info = port_details.get(port, {})
                if port in wsl_configs:
                    cfg = wsl_configs[port]
                    instances.append({
                        'name': cfg['name'],
                        'port': port,
                        'source': 'wsl',
                        'config_path': cfg.get('config_path', ''),
                        'config_content': cfg.get('config_content', ''),
                        'status': info.get('status', 'unknown'),
                        'uptime': info.get('uptime', 0),
                        'uptime_str': format_uptime(info.get('uptime', 0))
                    })
                else:
                    instances.append({
                        'name': f'端口-{port}',
                        'port': port,
                        'source': 'port-scan',
                        'config_path': '',
                        'config_content': '',
                        'status': info.get('status', 'unknown'),
                        'uptime': info.get('uptime', 0),
                        'uptime_str': format_uptime(info.get('uptime', 0)),
                        'warning': '无OpenClaw配置文件'
                    })
            
            # 保存缓存
            try:
                with open(os.path.join(SCRIPT_DIR, 'instances_cache.json'), 'w', encoding='utf-8') as f:
                    json.dump({
                        'instances': instances,
                        'timestamp': time.time()
                    }, f, ensure_ascii=False, indent=2)
            except:
                pass
            
            self.instances = instances
            
            update_progress('正在完成初始化...', f'共发现 {len(instances)} 个实例', 90)
            time.sleep(0.2)
            
            update_progress('初始化完成', f'✅ 发现 {len(instances)} 个实例 (点击扫描按钮重新扫描)', 100)
            
            # 延迟关闭splash
            time.sleep(0.5)
            splash.after(0, splash.destroy)
        
        thread = threading.Thread(target=background_scan, daemon=True)
        thread.start()
        
        # 不使用 mainloop()，改用 after() 让窗口自然更新并在扫描完成后关闭
        def check_thread():
            if not thread.is_alive():
                # 扫描完成，确保窗口关闭
                try:
                    splash.destroy()
                except:
                    pass
                return
            splash.after(100, check_thread)
        
        splash.after(200, check_thread)  # 延迟检查，避免过早
    
    def build_ui(self):
        # 标题
        Frame(self.root, bg='#2C3E50', height=50).pack(fill=X)
        Label(self.root, text=f'🛡️ {APP_NAME} v{VERSION}', 
              font=('Arial', 14, 'bold'), fg='white', bg='#2C3E50').place(x=10, y=12)
        
        # 控制栏
        bar = Frame(self.root, bg='#ECF0F1', height=40)
        bar.pack(fill=X, padx=10, pady=5)
        
        Button(bar, text='🔍 扫描', command=lambda: self.refresh(force=True), bg='#3498DB', fg='white', width=8).pack(side=LEFT, padx=3, pady=3)
        Button(bar, text='💾 备份', command=self.backup_all, bg='#27AE60', fg='white', width=8).pack(side=LEFT, padx=3, pady=3)
        Button(bar, text='📂 列表', command=self.show_backups, bg='#9B59B6', fg='white', width=8).pack(side=LEFT, padx=3, pady=3)
        
        self.status_lbl = Label(bar, text='🟡 扫描中...', font=('Arial', 10), fg='#7F8C8D', bg='#ECF0F1')
        self.status_lbl.pack(side=RIGHT)
        
        # 实例容器
        self.scroll_frame = Frame(self.root)
        self.scroll_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # 守护栏
        guard_frame = LabelFrame(self.root, text='⚡ 自动守护', font=('Arial', 10))
        guard_frame.pack(fill=X, padx=10, pady=5)
        
        self.guard_btn = Button(guard_frame, text='🟢 已开启', command=self.toggle_guard, bg='#27AE60', fg='white')
        self.guard_btn.pack(side=LEFT, padx=5, pady=5)
        Label(guard_frame, text=f'检测:{GUARD_INTERVAL}秒 | 重试:{MAX_RETRIES}次', fg='#7F8C8D').pack(side=LEFT, padx=20)
        
        # 日志
        log_frame = LabelFrame(self.root, text='📝 日志', font=('Arial', 10))
        log_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = Text(log_frame, font=('Consolas', 8))
        self.log_text.pack(fill=BOTH, expand=True, padx=5, pady=5)
    
    def log(self, msg):
        ts = datetime.now().strftime('%H:%M:%S')
        self.log_text.insert(END, f'[{ts}] {msg}\n')
        self.log_text.see(END)
        self.root.update()
    
    def refresh(self, force=False):
        """刷新实例列表
        
        Args:
            force: True=强制重新扫描（主界面进度条），False=直接用缓存刷新UI
        """
        if not force:
            # 非强制模式：直接用缓存刷新UI（无弹窗）
            self.log('🔍 加载缓存...')
            self.status_lbl.config(text='🟡 加载中...', fg='#F39C12')
            self.instances = discover_instances(force_rescan=False)
            self.refresh_ui()
            return
        
        # 强制模式：在主界面显示进度条（无弹窗）
        self.log('🔍 开始扫描...')
        self.status_lbl.config(text='🟡 扫描中...', fg='#F39C12')
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.cards = {}
        
        # 显示进度条区域
        progress_frame = Frame(self.scroll_frame, bg='#ECF0F1')
        progress_frame.pack(fill=X, pady=20)
        
        Label(progress_frame, text='🔍 正在扫描...', font=('Arial', 11, 'bold'), fg='#2C3E50').pack(pady=5)
        
        progress_lbl = Label(progress_frame, text='阶段1: 端口扫描', fg='#7F8C8D')
        progress_lbl.pack()
        
        # 进度条
        progress_bar_frame = Frame(progress_frame, bg='#BDC3C7', height=20)
        progress_bar_frame.pack(fill=X, padx=50, pady=10)
        progress_bar = Canvas(progress_bar_frame, bg='#BDC3C7', height=20)
        progress_bar.pack(fill=X, padx=5, pady=5)
        progress_bar_line = progress_bar.create_rectangle(5, 5, 5, 19, fill='#3498DB', outline='')
        
        pct_lbl = Label(progress_frame, text='0%', fg='#3498DB', font=('Consolas', 10))
        pct_lbl.pack()
        
        def update_progress(step, pct):
            progress_lbl.config(text=step)
            pct_lbl.config(text=f'{pct}%')
            bar_width = int(290 * pct / 100)
            progress_bar.coords(progress_bar_line, 5, 5, bar_width, 19)
            self.root.update()
        
        def do_refresh():
            try:
                update_progress('阶段1: 端口扫描...', 10)
                open_ports, port_details = scan_ports()
                update_progress(f'阶段2: WSL配置扫描 (发现{len(open_ports)}端口)...', 40)
                wsl_configs = scan_wsl_configs()
                update_progress('阶段3: 合并结果...', 70)
                
                # 合并结果（和 discover_instances 一样的逻辑）
                instances = []
                for port in open_ports:
                    info = port_details.get(port, {})
                    if port in wsl_configs:
                        cfg = wsl_configs[port]
                        instances.append({
                            'name': cfg['name'], 'port': port, 'source': 'wsl',
                            'config_path': cfg.get('config_path', ''),
                            'config_content': cfg.get('config_content', ''),
                            'status': info.get('status', 'unknown'),
                            'uptime': info.get('uptime', 0),
                            'uptime_str': format_uptime(info.get('uptime', 0))
                        })
                    else:
                        instances.append({
                            'name': f'端口-{port}', 'port': port, 'source': 'port-scan',
                            'config_path': '', 'config_content': '',
                            'status': info.get('status', 'unknown'),
                            'uptime': info.get('uptime', 0),
                            'uptime_str': format_uptime(info.get('uptime', 0)),
                            'warning': '无OpenClaw配置文件'
                        })
                
                # 保存缓存
                try:
                    with open(os.path.join(SCRIPT_DIR, 'instances_cache.json'), 'w', encoding='utf-8') as f:
                        json.dump({'instances': instances, 'timestamp': time.time()}, f, ensure_ascii=False, indent=2)
                except:
                    pass
                
                self.instances = instances
                update_progress('阶段4: 刷新界面...', 90)
                
                # 在主线程更新UI
                def update_ui():
                    progress_frame.destroy()
                    
                    if not self.instances:
                        Label(self.scroll_frame, text='❌ 未发现OpenClaw实例', font=('Arial', 14), fg='#E74C3C').pack(pady=50)
                        self.log('❌ 未发现实例')
                        self.status_lbl.config(text='❌ 无', fg='#E74C3C')
                        return
                    
                    openclaw = [i for i in self.instances if i.get('source') == 'wsl']
                    port_only = [i for i in self.instances if i.get('source') == 'port-scan']
                    
                    self.log(f'✅ 发现 {len(openclaw)} 个OpenClaw实例, {len(port_only)} 个仅端口开放')
                    self.status_lbl.config(text=f'🟢 OpenClaw:{len(openclaw)} | 端口:{len(port_only)}', fg='#27AE60')
                    
                    for inst in self.instances:
                        self.add_card(inst)
                
                self.root.after(0, update_ui)
            except Exception as e:
                log(f'扫描错误: {e}')
                progress_frame.destroy()
        
        thread = threading.Thread(target=do_refresh, daemon=True)
        thread.start()
    
    def refresh_ui(self):
        """直接刷新UI（无进度窗口，用于缓存加载后）"""
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.cards = {}
        
        if not self.instances:
            Label(self.scroll_frame, text='❌ 未发现OpenClaw实例', font=('Arial', 14), fg='#E74C3C').pack(pady=50)
            self.log('❌ 未发现实例')
            self.status_lbl.config(text='❌ 无', fg='#E74C3C')
            return
        
        openclaw = [i for i in self.instances if i.get('source') == 'wsl']
        port_only = [i for i in self.instances if i.get('source') == 'port-scan']
        
        self.log(f'✅ 发现 {len(openclaw)} 个OpenClaw实例, {len(port_only)} 个仅端口开放')
        self.status_lbl.config(text=f'🟢 OpenClaw:{len(openclaw)} | 端口:{len(port_only)}', fg='#27AE60')
        
        for inst in self.instances:
            self.add_card(inst)
    
    def add_card(self, inst):
        source = inst.get('source', 'unknown')
        is_openclaw = (source == 'wsl')
        
        if is_openclaw:
            title = f"📦 {inst['name']} ({inst['port']})"
        else:
            title = f"⚠️ 端口-{inst['port']} (非OpenClaw实例)"
        
        card = LabelFrame(self.scroll_frame, text=title, font=('Arial', 10))
        card.pack(fill=X, pady=3)
        
        online = check_health(inst['port'])
        color = '#27AE60' if online else '#E74C3C'
        status_icon = "🟢" if online else "🔴"
        
        if is_openclaw:
            config_icon = "✅配置" if inst.get('config_content') else "⚠️配置缺失"
            uptime_str = inst.get('uptime_str', 'N/A')
            info_txt = f'{status_icon} {"在线" if online else "离线"} | {config_icon} | 运行:{uptime_str}'
        else:
            info_txt = f'{status_icon} {"在线" if online else "离线"} | 无OpenClaw配置（可能是其他服务）'
        
        status_lbl = Label(card, text=info_txt, font=('Arial', 10, 'bold'), fg=color)
        status_lbl.pack(side=LEFT)
        
        if is_openclaw and inst.get('config_path'):
            full_path = inst['config_path']
            
            def copy_path(event, path=full_path):
                self.root.clipboard_clear()
                self.root.clipboard_append(path)
                self.root.update()
                log(f"📋 已复制: {path}")
                # 显示提示
                try:
                    import tkinter.messagebox as msgbox
                    msgbox.showinfo("已复制", f"路径已复制到剪贴板:\n{path}")
                except:
                    pass
            
            cfg_short = full_path.split('/')[-2:] if '/' in full_path else [full_path]
            path_lbl = Label(card, text=f'📁 .../{" /".join(cfg_short)}', font=('Arial', 8), fg='#3498DB', cursor='hand2')
            path_lbl.pack(side=RIGHT)
            path_lbl.bind('<Button-1>', copy_path)
        
        if is_openclaw:
            btns = Frame(card)
            btns.pack(fill=X, pady=5)
            for txt, cmd in [('▶启动', lambda i=inst: self.do_start(i)),
                            ('⏹停止', lambda i=inst: self.do_stop(i)),
                            ('🔄重启', lambda i=inst: self.do_restart(i)),
                            ('💾备份', lambda i=inst: self.do_backup(i))]:
                b = Button(btns, text=txt, width=8, bg='#3498DB', fg='white', command=cmd)
                b.pack(side=LEFT, padx=2)
        else:
            Label(card, text='此端口无OpenClaw配置，无法管理', font=('Arial', 8), fg='#95A5A6').pack(side=LEFT, pady=2)
        
        inst['_status_lbl'] = status_lbl
        inst['_online'] = online
        self.cards[inst['port']] = card
    
    def update_card(self, inst):
        online = check_health(inst['port'])
        inst['_online'] = online
        color = '#27AE60' if online else '#E74C3C'
        inst['_status_lbl'].config(text=f'状态: {"🟢在线" if online else "🔴离线"}', fg=color)
    
    def do_start(self, inst):
        self.log(f'▶ 启动 {inst["name"]}...')
        ok = start_gateway(inst)
        self.log(f'{"✅" if ok else "❌"} {"成功" if ok else "失败"}')
        self.update_card(inst)
    
    def do_stop(self, inst):
        self.log(f'⏹ 停止 {inst["name"]}...')
        ok = stop_gateway(inst)
        self.log(f'{"✅" if ok else "❌"} {"成功" if ok else "失败"}')
        self.update_card(inst)
    
    def do_restart(self, inst):
        self.log(f'🔄 重启 {inst["name"]}...')
        ok = restart_gateway(inst)
        self.log(f'{"✅" if ok else "❌"} {"成功" if ok else "失败"}')
        self.update_card(inst)
    
    def do_backup(self, inst):
        ok, msg = backup_instance(inst)
        if ok:
            self.log(f'💾 {inst["name"]} 备份成功')
            messagebox.showinfo('成功', f'备份到:\n{msg}')
        else:
            self.log(f'❌ 备份失败: {msg}')
    
    def backup_all(self):
        count = sum(1 for i in self.instances if backup_instance(i)[0])
        self.log(f'💾 备份完成: {count}/{len(self.instances)}')
        messagebox.showinfo('完成', f'已备份 {count} 个')
    
    def show_backups(self):
        backs = list_backups()
        
        win = Toplevel(self.root)
        win.title('📂 备份列表')
        win.geometry('450x350')
        
        Label(win, text=f'共 {len(backs)} 个备份', font=('Arial', 12)).pack()
        
        frame = Frame(win)
        frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        lb = Listbox(frame, font=('Consolas', 9))
        lb.pack(side=LEFT, fill=BOTH, expand=True)
        Scrollbar(frame, command=lb.yview).pack(side=RIGHT, fill=Y)
        lb.config(yscrollcommand=lambda f, y: lb.yview(f, y))
        
        files = []
        for b in backs:
            lb.insert(END, f"{b['name']} ({b['port']}) - {b['time']}")
            files.append(b)
        
        def do_restore():
            sel = lb.curselection()
            if sel:
                idx = sel[0]
                ok, msg = restore_instance(os.path.join(BACKUP_DIR, files[idx]['file']))
                if ok:
                    self.log(f'♻️ 已恢复')
                    messagebox.showinfo('成功', msg)
                    win.destroy()
                else:
                    messagebox.showerror('失败', msg)
        
        Frame(win).pack()
        Button(win, text='♻️ 恢复', command=do_restore, bg='#27AE60', fg='white').place(x=180, y=310)
        Button(win, text='关闭', command=win.destroy).place(x=250, y=310)
    
    def start_guard(self):
        self.guard_on = True
        self.guard_thread = threading.Thread(target=self.guard_loop, daemon=True)
        self.guard_thread.start()
        self.log('🛡️ 守护已启动')
        self.guard_btn.config(text='🟢 已开启', bg='#27AE60')
    
    def stop_guard(self):
        self.guard_on = False
        if self.guard_thread:
            self.guard_thread.join(timeout=1)
        self.log('🛡️ 守护已关闭')
        self.guard_btn.config(text='🔴 已关闭', bg='#E74C3C')
    
    def toggle_guard(self):
        if self.guard_on:
            self.stop_guard()
        else:
            self.start_guard()
    
    def guard_loop(self):
        retry = {}
        while self.guard_on:
            for inst in self.instances:
                p, n = inst['port'], inst['name']
                if not check_health(p):
                    retry[p] = retry.get(p, 0) + 1
                    if retry[p] == 1:
                        self.log(f'⚠️ {n} 离线，尝试重启...')
                        restart_gateway(inst)
                    elif retry[p] >= MAX_RETRIES:
                        self.log(f'⚠️ {n} 重启失败({retry[p]}次)')
                else:
                    if retry.get(p, 0) > 0:
                        self.log(f'✅ {n} 已恢复')
                    retry[p] = 0
                    self.root.after(0, lambda i=inst: self.update_card(i))
            time.sleep(GUARD_INTERVAL)
    
    def run(self):
        self.log(f'🚀 {APP_NAME} v{VERSION} 已启动')
        self.root.mainloop()

if __name__ == '__main__':
    show_banner()
    App().run()