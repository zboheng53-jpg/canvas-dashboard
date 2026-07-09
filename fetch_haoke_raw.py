"""
Fetch linear algebra homework questions from haoke as raw LaTeX JSON.
For each task:
  1. Navigate to practiceResult via CDP, click 查看详情 to get submitId
  2. Call /api/learn/task/exercise/querySubmit to get raw question data (LaTeX intact)
  3. Save to data/task_{taskId}_raw.json
"""
import requests, json, time, sys, re, os

CDP = 'http://localhost:3456'
BASE = 'https://tongji.aihaoke.net'
INSTANCE_ID = 10893
COURSE_ID = 22806

TASK_MAP = {
    163602: '习题1.1_矩阵及其运算',
    163604: '习题1.2_矩阵的分块与初等方阵',
    163601: '习题1.3_矩阵的秩',
    165214: '习题1.4_线性方程组',
    163568: '习题2.1_行列式的定义',
    163569: '习题2.2_行列式的性质',
    163570: '习题2.3_行列式按行列展开',
    163571: '习题2.4_Cramer法则',
    163577: '习题3.1_向量的线性相关性',
    163578: '习题3.2_向量组的秩',
    163574: '习题3.3_线性方程组解的结构',
    163579: '习题3.4_向量空间',
    183544: '习题4.1_线性空间的定义与性质',
    163581: '习题4.2_线性空间的基与维数',
    183545: '习题4.3_基变换与坐标变换',
    163582: '习题4.4_线性子空间',
    163583: '习题4.5_子空间的直和',
    183550: '习题4.6_线性空间的同构',
    187311: '习题5.1_线性变换的定义与性质',
    163585: '习题5.2_线性变换的矩阵表示',
    163586: '习题5.3_线性变换的值域与核',
    163587: '习题5.4_不变子空间',
    163588: '习题5.5_线性变换的特征值',
    163591: '习题6.1_特征值与特征向量',
    163592: '习题6.2_矩阵的对角化',
    163593: '习题6.3_实对称矩阵的对角化',
    163594: '习题6.4_二次型',
    163595: '习题7.1_内积空间',
    163596: '习题7.2_标准正交基与矩阵的QR分解',
    163599: '习题8.1_二次型及其标准形',
    163600: '习题8.2_正定二次型',
}


def cdp(target_id, js, timeout=10):
    r = requests.post(f'{CDP}/eval?target={target_id}', data=js, timeout=timeout)
    val = r.text
    if val.startswith('{"value"'):
        return json.loads(val).get('value', '')
    if val.startswith('{"error"'):
        return None
    try:
        return json.loads(val)
    except Exception:
        return val


def get_submit_id(target_id, task_id):
    url = f'{BASE}/student/course/{COURSE_ID}/studyTask/{task_id}/practiceResult?taskId={task_id}&instanceId={INSTANCE_ID}'
    requests.get(f'{CDP}/navigate?target={target_id}&url={url}', timeout=20)
    time.sleep(7)

    result = cdp(target_id, '''
    (function(){
        window.__nc = [];
        var op = history.pushState;
        history.pushState = function(s,t,u){ window.__nc.push(u); return op.apply(this,arguments); };
        var btn = document.querySelector("button.el-button--primary");
        if(btn){ btn.click(); return "ok"; }
        return "no_button";
    })()''')

    if 'no_button' in str(result or ''):
        return None

    time.sleep(6)
    navs_raw = cdp(target_id, 'JSON.stringify(window.__nc)')
    current = cdp(target_id, 'location.href') or ''

    urls = [current]
    try:
        navs = json.loads(navs_raw) if isinstance(navs_raw, str) else (navs_raw or [])
        if isinstance(navs, list):
            urls += navs
    except Exception:
        pass

    for u in urls:
        m = re.search(r'submitId=(\d+)', str(u))
        if m:
            return m.group(1)
    return None


def fetch_quiz_data(token, submit_id):
    r = requests.post(
        f'{BASE}/api/learn/task/exercise/querySubmit',
        headers={'Content-Type': 'application/json',
                 'Authorization': f'Bearer {token}',
                 '__tenant__': 'tongji'},
        json={'submitId': int(submit_id), 'requestId': f'r{submit_id}'},
        timeout=20,
    )
    d = r.json()
    if d.get('code') == 200:
        return d.get('data')
    print(f'  API error: {d.get("message")}')
    return None


def main():
    targets = json.loads(requests.get(f'{CDP}/targets', timeout=5).text)
    target = next((t for t in targets if 'tongji.aihaoke.net' in t['url']), None)
    if not target:
        print('ERROR: No haoke browser tab found.')
        sys.exit(1)
    tid = target['targetId']
    print(f'Target: {tid}')

    cookie = cdp(tid, 'document.cookie') or ''
    m = re.search(r'haoke-token=([^\s;]+)', cookie)
    if not m:
        print('ERROR: No haoke-token in cookies.')
        sys.exit(1)
    token = m.group(1)
    print(f'Token OK (len={len(token)})')

    task_ids = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else list(TASK_MAP.keys())
    done = 0

    for task_id in task_ids:
        name = TASK_MAP.get(task_id, str(task_id))
        print(f'\n[{task_id}] {name}')
        out = f'data/task_{task_id}_raw.json'

        # Skip if already fetched
        if os.path.exists(out):
            try:
                existing = json.loads(open(out, encoding='utf-8').read())
                if existing.get('quizList'):
                    print(f'  Skip (already have {len(existing["quizList"])} quizzes)')
                    done += 1
                    continue
            except Exception:
                pass

        submit_id = get_submit_id(tid, task_id)
        if not submit_id:
            print(f'  FAILED: no submitId')
            continue
        print(f'  submitId={submit_id}')

        data = fetch_quiz_data(token, submit_id)
        if not data:
            print(f'  FAILED: no data')
            continue

        n = len(data.get('quizList', []))
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'  Saved {n} quizzes → {out}')
        done += 1
        time.sleep(2)

    print(f'\nDone: {done}/{len(task_ids)}')

main()
