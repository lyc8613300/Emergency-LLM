"""
Emergency-LLM 微调API
基于 LLaMA-Factory 后端的微调接口
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import subprocess
import json
import os
import time
import threading
from typing import Dict, Any, Optional
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')
CORS(app)

# 全局变量存储训练状态
training_status = {
    'status': 'idle',  # idle, training, completed, error
    'task_id': None,
    'epoch': 0,
    'step': 0,
    'total_steps': 0,
    'loss': 0.0,
    'learning_rate': 0.0,
    'progress': 0.0,
    'logs': [],
    'error': None,
    'process': None
}

# 配置文件路径
CONFIG_DIR = 'configs'
OUTPUT_DIR = 'saves'
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def clean_path(path: str) -> str:
    """
    清理路径字符串：去除引号、空格和末尾斜杠
    """
    if not path:
        return path
    # 去除首尾空格
    path = path.strip()
    # 去除引号（单引号和双引号）
    path = path.strip('"').strip("'")
    # 去除末尾的斜杠
    path = path.rstrip('/')
    return path


def convert_config_to_cli_args(config: Dict[str, Any]) -> list:
    """
    将前端配置转换为LLaMA-Factory命令行参数
    """
    args = ['llamafactory-cli', 'train']
    
    # 模型配置 - 优先使用 model_path（本地路径），其次才使用 model_name
    if config.get('model_path') and config['model_path'].strip():
        # 如果提供了模型路径，优先使用本地路径
        model_path = clean_path(config['model_path'])
        args.extend(['--model_name_or_path', model_path])
    elif config.get('model_name') and config['model_name'] != 'custom':
        # 如果只提供了模型名称，使用模型名称
        model_name = clean_path(config['model_name'])
        args.extend(['--model_name_or_path', model_name])
    
    # 微调类型
    if config.get('finetuning_type'):
        args.extend(['--finetuning_type', config['finetuning_type']])
    
    # 数据集配置
    if config.get('dataset'):
        if isinstance(config['dataset'], list):
            # 清理数据集名称中的空格
            datasets = [d.strip() for d in config['dataset'] if d.strip()]
            args.extend(['--dataset', ','.join(datasets)])
        else:
            args.extend(['--dataset', config['dataset'].strip()])
    
    if config.get('dataset_dir'):
        dataset_dir = clean_path(config['dataset_dir'])
        args.extend(['--dataset_dir', dataset_dir])
    
    # 训练阶段
    if config.get('training_stage'):
        args.extend(['--stage', config['training_stage']])
    
    # 基础训练参数
    if config.get('learning_rate'):
        args.extend(['--learning_rate', str(config['learning_rate'])])
    
    if config.get('num_train_epochs'):
        args.extend(['--num_train_epochs', str(config['num_train_epochs'])])
    
    if config.get('max_grad_norm'):
        args.extend(['--max_grad_norm', str(config['max_grad_norm'])])
    
    if config.get('cutoff_len'):
        args.extend(['--cutoff_len', str(config['cutoff_len'])])
    
    if config.get('batch_size'):
        args.extend(['--per_device_train_batch_size', str(config['batch_size'])])
    
    if config.get('gradient_accumulation_steps'):
        args.extend(['--gradient_accumulation_steps', str(config['gradient_accumulation_steps'])])
    
    if config.get('val_size') and config['val_size'] > 0:
        args.extend(['--val_size', str(config['val_size'])])
    
    if config.get('lr_scheduler_type'):
        args.extend(['--lr_scheduler_type', config['lr_scheduler_type']])
    
    # 计算精度
    if config.get('compute_type'):
        if config['compute_type'] == 'bf16':
            args.append('--bf16')
        elif config['compute_type'] == 'fp16':
            args.append('--fp16')
    
    # 量化配置
    if config.get('quantization_bit') and config['quantization_bit'] != 'none':
        args.extend(['--quantization_bit', config['quantization_bit']])
    
    # Template
    if config.get('template'):
        args.extend(['--template', config['template']])
    
    # LoRA配置
    if config.get('finetuning_type') == 'lora':
        if config.get('lora_rank'):
            args.extend(['--lora_rank', str(config['lora_rank'])])
        
        if config.get('lora_alpha'):
            args.extend(['--lora_alpha', str(config['lora_alpha'])])
        
        if config.get('lora_dropout'):
            args.extend(['--lora_dropout', str(config['lora_dropout'])])
        
        if config.get('lora_target'):
            args.extend(['--lora_target', config['lora_target']])
        
        if config.get('use_rslora'):
            args.append('--use_rslora')
        
        if config.get('use_dora'):
            args.append('--use_dora')
    
    # 高级选项
    if config.get('logging_steps'):
        args.extend(['--logging_steps', str(config['logging_steps'])])
    
    if config.get('save_steps'):
        args.extend(['--save_steps', str(config['save_steps'])])
    
    if config.get('warmup_steps'):
        args.extend(['--warmup_steps', str(config['warmup_steps'])])
    
    if config.get('output_dir'):
        output_dir = clean_path(config['output_dir'])
        args.extend(['--output_dir', output_dir])
    else:
        args.extend(['--output_dir', os.path.join(OUTPUT_DIR, f'train_{int(time.time())}')])
    
    # DeepSpeed
    if config.get('ds_stage') and config['ds_stage'] != 'none':
        args.extend(['--deepspeed', f'ds_z{config["ds_stage"]}_config.json'])
        
        if config.get('ds_offload'):
            args.append('--deepspeed_offload')
    
    # 报告工具
    if config.get('report_to') and config['report_to'] != 'none':
        args.extend(['--report_to', config['report_to']])
    
    # 布尔选项
    if config.get('packing'):
        args.append('--packing')
    
    if config.get('train_on_prompt'):
        args.append('--train_on_prompt')
    
    if config.get('resize_vocab'):
        args.append('--resize_vocab')
    
    # 添加其他必要参数
    args.append('--do_train')
    args.extend(['--overwrite_output_dir', 'True'])
    
    return args


def parse_training_log(line: str) -> Optional[Dict[str, Any]]:
    """
    解析训练日志，提取关键信息
    支持的格式:
    - {'loss': 2.5, 'learning_rate': 5e-05, 'epoch': 1.0}
    - Step 100/1000: loss=2.5
    """
    try:
        result = {}
        
        # 方法1: 解析包含 'loss' 的 JSON 格式日志（支持单引号和双引号）
        if 'loss' in line.lower() and '{' in line and '}' in line:
            # 提取 JSON 部分
            start_idx = line.find('{')
            end_idx = line.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = line[start_idx:end_idx]
                try:
                    # 尝试直接解析
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    try:
                        # 如果失败，尝试将单引号替换为双引号
                        json_str = json_str.replace("'", '"')
                        data = json.loads(json_str)
                    except:
                        data = None
                
                if data:
                    # 提取 loss
                    if 'loss' in data:
                        result['loss'] = float(data['loss'])
                    
                    # 提取 epoch
                    if 'epoch' in data:
                        result['epoch'] = float(data['epoch'])
                    
                    # 提取 step
                    if 'step' in data:
                        result['step'] = int(data['step'])
                    elif 'global_step' in data:
                        result['step'] = int(data['global_step'])
                    
                    # 提取学习率
                    if 'learning_rate' in data:
                        result['learning_rate'] = float(data['learning_rate'])
        
        # 方法2: 解析百分比进度 (例如: "10%|████      | 100/1000")
        if '%|' in line:
            import re
            match = re.search(r'(\d+)%', line)
            if match:
                progress = int(match.group(1))
                result['progress'] = progress / 100.0
            
            # 提取步数 (例如: 100/1000)
            match = re.search(r'(\d+)/(\d+)', line)
            if match:
                current_step = int(match.group(1))
                total_steps = int(match.group(2))
                result['step'] = current_step
                result['total_steps'] = total_steps
                result['progress'] = current_step / total_steps if total_steps > 0 else 0
        
        # 方法3: 解析关键词格式 (例如: "Step 100: loss=2.5")
        if 'step' in line.lower() and 'loss' in line.lower():
            import re
            
            # 提取 step 数字
            step_match = re.search(r'[Ss]tep\s+(\d+)', line)
            if step_match:
                result['step'] = int(step_match.group(1))
            
            # 提取 loss 数值
            loss_match = re.search(r'loss[:\s=]+(\d+\.?\d*)', line, re.IGNORECASE)
            if loss_match:
                result['loss'] = float(loss_match.group(1))
        
        # 方法4: 解析 epoch 信息
        if 'epoch' in line.lower():
            import re
            epoch_match = re.search(r'[Ee]poch[:\s]+(\d+\.?\d*)', line)
            if epoch_match:
                result['epoch'] = float(epoch_match.group(1))
        
        return result if result else None
        
    except Exception as e:
        logger.error(f"解析日志失败: {e}")
        return None


def monitor_training_process(process: subprocess.Popen, task_id: str):
    """
    监控训练进程，更新状态
    """
    global training_status
    
    try:
        # 读取进程输出
        for line in iter(process.stdout.readline, b''):
            if line:
                decoded_line = line.decode('utf-8').strip()
                
                # 记录原始日志（用于调试）
                logger.info(decoded_line)
                
                # 添加到日志列表
                training_status['logs'].append(decoded_line)
                
                # 只保留最近50条日志
                if len(training_status['logs']) > 50:
                    training_status['logs'].pop(0)
                
                # 解析训练指标
                parsed = parse_training_log(decoded_line)
                if parsed:
                    # 更新训练状态，但不覆盖未提供的字段
                    if 'loss' in parsed:
                        training_status['loss'] = parsed['loss']
                        logger.info(f"更新 Loss: {parsed['loss']}")
                    
                    if 'epoch' in parsed:
                        training_status['epoch'] = parsed['epoch']
                        logger.info(f"更新 Epoch: {parsed['epoch']}")
                    
                    if 'step' in parsed:
                        training_status['step'] = parsed['step']
                        logger.info(f"更新 Step: {parsed['step']}")
                    
                    if 'progress' in parsed:
                        training_status['progress'] = parsed['progress']
                        logger.info(f"更新进度: {parsed['progress']:.2%}")
                    
                    if 'learning_rate' in parsed:
                        training_status['learning_rate'] = parsed['learning_rate']
        
        # 等待进程结束
        return_code = process.wait()
        
        if return_code == 0:
            training_status['status'] = 'completed'
            training_status['progress'] = 1.0
            training_status['logs'].append("✅ 训练成功完成！")
            logger.info("训练完成")
        else:
            training_status['status'] = 'error'
            training_status['error'] = f"训练进程异常退出，返回码: {return_code}"
            training_status['logs'].append(f"❌ 训练失败：{training_status['error']}")
            logger.error(training_status['error'])
            
    except Exception as e:
        training_status['status'] = 'error'
        training_status['error'] = str(e)
        training_status['logs'].append(f"❌ 监控异常：{str(e)}")
        logger.error(f"监控训练进程失败: {e}")
    
    finally:
        training_status['process'] = None


@app.route('/')
def index():
    """主页 - 返回微调界面"""
    return send_from_directory('static', 'finetune.html')


@app.route('/api/train/start', methods=['POST'])
def start_training():
    """
    开始训练
    """
    global training_status
    
    # 检查是否已有训练在进行
    if training_status['status'] == 'training':
        return jsonify({
            'error': '已有训练任务在进行中'
        }), 400
    
    try:
        config = request.json
        logger.info(f"收到训练请求: {json.dumps(config, indent=2, ensure_ascii=False)}")
        
        # 验证配置
        if not config.get('model_name') and not config.get('model_path'):
            return jsonify({'error': '必须指定模型名称或路径'}), 400
        
        if not config.get('dataset'):
            return jsonify({'error': '必须指定数据集'}), 400
        
        # 生成任务ID
        task_id = f"train_{int(time.time())}"
        
        # 保存配置
        config_path = os.path.join(CONFIG_DIR, f'{task_id}.json')
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # 转换为命令行参数
        cli_args = convert_config_to_cli_args(config)
        
        # 确定实际使用的模型路径
        actual_model = None
        if config.get('model_path') and config['model_path'].strip():
            actual_model = config['model_path']
            logger.info(f"使用本地模型路径: {actual_model}")
        elif config.get('model_name') and config['model_name'] != 'custom':
            actual_model = config['model_name']
            logger.info(f"使用模型名称: {actual_model}")
        
        logger.info(f"训练命令: {' '.join(cli_args)}")
        
        # 重置训练状态
        training_status = {
            'status': 'training',
            'task_id': task_id,
            'epoch': 0,
            'step': 0,
            'total_steps': 0,
            'loss': 0.0,
            'learning_rate': 0.0,
            'progress': 0.0,
            'logs': [
                f"🚀 任务ID: {task_id}",
                f"📝 模型: {actual_model or 'N/A'}",
                f"📊 数据集: {', '.join(config.get('dataset', []))}",
                f"⚙️  训练命令: {' '.join(cli_args)}"
            ],
            'error': None,
            'process': None
        }
        
        # 设置 GPU 设备
        env = os.environ.copy()
        if config.get('cuda_device') is not None:
            # 如果指定了 GPU 设备，使用指定的值
            cuda_device = str(config['cuda_device'])
            env['CUDA_VISIBLE_DEVICES'] = cuda_device
            logger.info(f"使用指定的 GPU 设备: CUDA_VISIBLE_DEVICES={cuda_device}")
        else:
            # 未指定时使用系统默认（所有可用GPU）
            logger.info(f"未指定GPU设备，使用系统默认配置")
        
        # 启动训练进程
        process = subprocess.Popen(
            cli_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            env=env
        )
        
        training_status['process'] = process
        
        # 在后台线程中监控训练进程
        monitor_thread = threading.Thread(
            target=monitor_training_process,
            args=(process, task_id)
        )
        monitor_thread.daemon = True
        monitor_thread.start()
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '训练已启动'
        })
        
    except Exception as e:
        logger.error(f"启动训练失败: {e}")
        return jsonify({
            'error': str(e)
        }), 500


@app.route('/api/train/stop', methods=['POST'])
def stop_training():
    """
    停止训练
    """
    global training_status
    
    try:
        if training_status['status'] != 'training':
            return jsonify({'error': '没有正在进行的训练'}), 400
        
        process = training_status.get('process')
        if process:
            process.terminate()
            process.wait(timeout=10)
        
        training_status['status'] = 'idle'
        training_status['logs'].append("训练已被用户停止")
        
        return jsonify({
            'success': True,
            'message': '训练已停止'
        })
        
    except Exception as e:
        logger.error(f"停止训练失败: {e}")
        return jsonify({
            'error': str(e)
        }), 500


@app.route('/api/train/status', methods=['GET'])
def get_training_status():
    """
    获取训练状态
    """
    task_id = request.args.get('task_id')
    
    # 返回当前训练状态
    status_copy = training_status.copy()
    
    # 移除process对象（不可序列化）
    status_copy.pop('process', None)
    
    # 只返回最新的10条日志
    if len(status_copy['logs']) > 10:
        status_copy['logs'] = status_copy['logs'][-10:]
    
    return jsonify(status_copy)


@app.route('/api/export', methods=['POST'])
def export_model():
    """
    导出模型（合并 LoRA 适配器与基础模型）
    """
    try:
        config = request.json
        logger.info(f"收到导出请求: {json.dumps(config, indent=2, ensure_ascii=False)}")
        
        # 验证必填参数
        if not config.get('checkpoint_path'):
            return jsonify({
                'error': '请指定检查点路径 (checkpoint_path)'
            }), 400
        
        if not config.get('export_path'):
            return jsonify({
                'error': '请指定导出路径 (export_path)'
            }), 400
        
        checkpoint_path = clean_path(config['checkpoint_path'])
        
        # 检查是否为 LoRA 适配器（检查是否存在 adapter_config.json）
        adapter_config_path = os.path.join(checkpoint_path, 'adapter_config.json')
        is_adapter = os.path.exists(adapter_config_path)
        
        # 构建导出命令
        args = ['llamafactory-cli', 'export']
        
        if is_adapter:
            # 如果是 LoRA 适配器，需要读取基础模型路径
            try:
                with open(adapter_config_path, 'r', encoding='utf-8') as f:
                    adapter_config = json.load(f)
                    base_model_path = adapter_config.get('base_model_name_or_path')
                    
                    if not base_model_path:
                        return jsonify({
                            'error': '无法从 adapter_config.json 中获取基础模型路径'
                        }), 400
                    
                    # 如果前端提供了基础模型路径，使用前端的；否则使用配置文件中的
                    if config.get('base_model_path'):
                        base_model_path = clean_path(config['base_model_path'])
                    
                    logger.info(f"检测到 LoRA 适配器，基础模型: {base_model_path}")
                    args.extend(['--model_name_or_path', base_model_path])
                    args.extend(['--adapter_name_or_path', checkpoint_path])
                    
            except Exception as e:
                return jsonify({
                    'error': f'读取 adapter_config.json 失败: {str(e)}'
                }), 400
        else:
            # 如果是完整模型，直接导出
            logger.info(f"检测到完整模型，直接导出")
            args.extend(['--model_name_or_path', checkpoint_path])
        
        export_path = clean_path(config['export_path'])
        args.extend(['--export_dir', export_path])
        
        # 导出设备（auto 可以利用 GPU 加速）
        export_device = config.get('export_device', 'auto')
        args.extend(['--export_device', export_device])
        
        # 其他可选参数
        if config.get('export_size'):
            args.extend(['--export_size', str(config['export_size'])])
        
        if config.get('export_quantization_bit'):
            args.extend(['--export_quantization_bit', str(config['export_quantization_bit'])])
        
        logger.info(f"导出命令: {' '.join(args)}")
        
        # 执行导出
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=3600  # 1小时超时
        )
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'message': '模型导出成功',
                'output': result.stdout,
                'export_path': export_path
            })
        else:
            return jsonify({
                'error': '导出失败',
                'details': result.stderr
            }), 500
            
    except Exception as e:
        logger.error(f"导出模型失败: {e}")
        return jsonify({
            'error': str(e)
        }), 500


@app.route('/api/datasets', methods=['GET'])
def list_datasets():
    """
    列出可用的数据集
    根据指定的 dataset_dir 读取 dataset_info.json 文件，返回数据集列表及其详细信息
    """
    try:
        dataset_dir = request.args.get('dataset_dir', 'data')
        dataset_dir = clean_path(dataset_dir)
        
        # 读取dataset_info.json
        dataset_info_path = os.path.join(dataset_dir, 'dataset_info.json')
        
        if os.path.exists(dataset_info_path):
            with open(dataset_info_path, 'r', encoding='utf-8') as f:
                dataset_info = json.load(f)
            
            # 构建数据集列表，包含更多信息
            datasets = []
            for name, info in dataset_info.items():
                datasets.append({
                    'name': name,
                    'file_name': info.get('file_name', ''),
                    'file_sha1': info.get('file_sha1', ''),
                    'ranking': info.get('ranking', True),
                    'formatting': info.get('formatting', 'alpaca')
                })
            
            return jsonify({
                'success': True,
                'datasets': datasets,
                'dataset_dir': dataset_dir,
                'total': len(datasets)
            })
        else:
            logger.warning(f"数据集信息文件不存在: {dataset_info_path}")
            return jsonify({
                'success': False,
                'datasets': [],
                'dataset_dir': dataset_dir,
                'total': 0,
                'message': f'未找到 dataset_info.json 文件，请确认目录 {dataset_dir} 是否正确'
            })
            
    except Exception as e:
        logger.error(f"列出数据集失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'datasets': [],
            'total': 0
        }), 500


@app.route('/api/config/save', methods=['POST'])
def save_config():
    """
    保存训练配置
    """
    try:
        config = request.json
        config_name = config.get('config_name', f'config_{int(time.time())}')
        
        config_path = os.path.join(CONFIG_DIR, f'{config_name}.json')
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        return jsonify({
            'success': True,
            'message': f'配置已保存到 {config_path}'
        })
        
    except Exception as e:
        logger.error(f"保存配置失败: {e}")
        return jsonify({
            'error': str(e)
        }), 500


@app.route('/api/config/list', methods=['GET'])
def list_configs():
    """
    列出所有保存的配置
    """
    try:
        configs = []
        
        if os.path.exists(CONFIG_DIR):
            for filename in os.listdir(CONFIG_DIR):
                if filename.endswith('.json'):
                    configs.append(filename[:-5])  # 移除.json后缀
        
        return jsonify({
            'success': True,
            'configs': configs
        })
        
    except Exception as e:
        logger.error(f"列出配置失败: {e}")
        return jsonify({
            'error': str(e)
        }), 500


if __name__ == '__main__':
    print("="*60)
    print("Emergency-LLM 微调API服务器")
    print("="*60)
    print(f"访问地址: http://localhost:5000")
    print(f"配置目录: {os.path.abspath(CONFIG_DIR)}")
    print(f"输出目录: {os.path.abspath(OUTPUT_DIR)}")
    print("="*60)
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    )

