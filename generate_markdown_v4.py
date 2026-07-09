"""
Generate clean markdown from haoke raw JSON (v4).
Source: data/task_{taskId}_raw.json (fetched by fetch_haoke_raw.py)
Output: markdown files with raw LaTeX intact ($...$ and $$...$$).

The JSON already has clean LaTeX in `content` and `solution` fields —
no KaTeX innerText parsing needed.
"""
import os, re, json, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

INPUT_DIR  = r'C:\Users\zhangboheng\Desktop\canvas-dashboard\data'
OUTPUT_DIR = r'C:\Users\zhangboheng\Desktop\同济\复习资料\线性代数作业'

TASK_MAP = {
    163602: '习题1.1_矩阵及其运算',
    163604: '习题1.2_矩阵的分块与初等方阵',
    163601: '习题1.3_矩阵的秩',
    165214: '习题1.4_线性方程组',
    163603: '习题1.5_自测题',
    163568: '习题2.1_行列式的定义',
    163569: '习题2.2_行列式的性质',
    163570: '习题2.3_行列式按行列展开',
    163571: '习题2.4_Cramer法则',
    171853: '习题2.5_自测题',
    163577: '习题3.1_向量的线性相关性',
    163578: '习题3.2_向量组的秩',
    163574: '习题3.3_线性方程组解的结构',
    163579: '习题3.4_向量空间',
    163580: '习题3.5_自测题',
    183544: '习题4.1_线性空间的定义与性质',
    163581: '习题4.2_线性空间的基与维数',
    183545: '习题4.3_基变换与坐标变换',
    163582: '习题4.4_线性子空间',
    163583: '习题4.5_子空间的直和',
    183550: '习题4.6_线性空间的同构',
    163584: '习题4.7_自测题',
    187311: '习题5.1_线性变换的定义与性质',
    163585: '习题5.2_线性变换的矩阵表示',
    163586: '习题5.3_线性变换的值域与核',
    163587: '习题5.4_不变子空间',
    163588: '习题5.5_线性变换的特征值',
    163590: '习题5.6_自测题',
    163591: '习题6.1_特征值与特征向量',
    163592: '习题6.2_矩阵的对角化',
    163593: '习题6.3_实对称矩阵的对角化',
    163594: '习题6.4_二次型',
    192045: '习题6.5_自测题',
    163595: '习题7.1_内积空间',
    163596: '习题7.2_标准正交基与矩阵的QR分解',
    163597: '习题7.3_正交子空间',
    163598: '习题7.4_保长同构酉变换与酉相似',
    163599: '习题8.1_二次型及其标准形',
    163600: '习题8.2_正定二次型',
}

QUIZ_TYPE_NAMES = {
    10: '单选题', 20: '多选题', 30: '判断题', 40: '填空题',
    50: '简答题', 60: '计算题', 70: '证明题', 100: '复合题',
}

WRITING_SPACE = '\n\n\n\n\n\n'   # ~6 blank lines for handwriting


def clean_content(text):
    """Light cleanup: normalize whitespace, strip trailing spaces."""
    if not text:
        return ''
    # Normalize \r\n to \n
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Strip trailing spaces from each line
    lines = [l.rstrip() for l in text.split('\n')]
    # Collapse 3+ blank lines to 2
    out = []
    blanks = 0
    for l in lines:
        if l == '':
            blanks += 1
            if blanks <= 2:
                out.append('')
        else:
            blanks = 0
            out.append(l)
    return '\n'.join(out).strip()


def format_quiz(q, q_num, sub_num=None):
    """Format a single quiz item into markdown."""
    content = clean_content(q.get('content', ''))
    solution = clean_content(q.get('solution', ''))
    quiz_type = q.get('quizType', 0)
    type_name = QUIZ_TYPE_NAMES.get(quiz_type, '')

    lines = []

    # Number prefix
    if sub_num is not None:
        prefix = f'({sub_num})'
    else:
        prefix = f'{q_num}.'

    if content:
        # Put the number inline with content if content starts on first line
        first_line = content.split('\n')[0]
        rest = '\n'.join(content.split('\n')[1:])
        lines.append(f'{prefix} {first_line}')
        if rest.strip():
            lines.append(rest)
    else:
        lines.append(prefix)

    if solution:
        lines.append('')
        lines.append('**参考答案**')
        lines.append('')
        lines.append(solution)

    return '\n'.join(lines)


def format_file(data, task_name):
    title = task_name.replace('_', ' ')
    md = f'# {title}\n\n'
    md += '> 来源：同济大学好课平台 · 线性代数（荣）\n\n'
    md += '---\n\n'

    quiz_list = data.get('quizList', [])
    q_num = 0

    for q in quiz_list:
        quiz_type = q.get('quizType', 0)
        sub_list = q.get('subList') or []

        if quiz_type == 100 and sub_list:
            # Composite question: parent has stem, children have sub-questions
            q_num += 1
            parent_content = clean_content(q.get('content', ''))
            md += f'## 第 {q_num} 题\n\n'
            if parent_content:
                md += parent_content + '\n\n'

            for sub in sub_list:
                sub_content = clean_content(sub.get('content', ''))
                sub_solution = clean_content(sub.get('solution', ''))

                if sub_content:
                    md += sub_content + '\n'

                if sub_solution:
                    md += '\n**参考答案**\n\n'
                    md += sub_solution + '\n'

                md += '\n'

        else:
            # Simple question
            q_num += 1
            content = clean_content(q.get('content', ''))
            solution = clean_content(q.get('solution', ''))

            md += f'## 第 {q_num} 题\n\n'
            if content:
                md += content + '\n'
            if solution:
                md += '\n**参考答案**\n\n'
                md += solution + '\n'

        md += WRITING_SPACE
        md += '\n---\n\n'

    return md


os.makedirs(OUTPUT_DIR, exist_ok=True)

processed = 0
for task_id, task_name in sorted(TASK_MAP.items()):
    raw_file = os.path.join(INPUT_DIR, f'task_{task_id}_raw.json')
    if not os.path.exists(raw_file):
        print(f'SKIP (no raw JSON): {task_name}')
        continue

    with open(raw_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data.get('quizList'):
        print(f'SKIP (empty quizList): {task_name}')
        continue

    md = format_file(data, task_name)

    out_file = os.path.join(OUTPUT_DIR, f'{task_name}.md')
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(md)

    lines = md.count('\n')
    print(f'OK  {task_name}.md  ({len(md)} chars, {lines} lines)')
    processed += 1

print(f'\nDone! {processed} files generated.')
