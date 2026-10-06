# -*- coding: utf-8 -*-
"""AIM 2627 Python Coursework —— 哨兵 Sentry 控制模块（学生骨架）。

你的全部作业都在本文件里：按题面（题面.pdf）各题的规范补全每个标有 TODO 的函数。
- 骨架已提供：Facing / SentryState 枚举、SentryGrid 的构造与只读属性、
  渲染函数 render_frame（demo 用，不进测试）。
- 你要实现：Q1-Q6 与 Bonus 的全部 TODO，以及 SentryGrid 的
  四个方法（current_pos 的 setter、move_forward、turn_left、turn_right）。
- 未实现的函数 raise NotImplementedError：可见测试会自动 skip，
  CI 一开始就是绿的；实现一个，对应测试亮一个。
- `python main.py`（或 PYTHONPATH=src python -m main）可看 ASCII 演示。
"""
import json
from collections import deque
from enum import Enum


# ---------------------------------------------------------------------------
# 仿真世界基础（已提供，勿改）
# ---------------------------------------------------------------------------
class Facing(Enum):
    """朝向枚举。世界坐标 (x, y)：x 向右增长，y 向上增长（数学系）。"""

    UP = (0, 1)
    DOWN = (0, -1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def delta(self):
        """该朝向的单位位移向量 (dx, dy)。"""
        return self.value[0], self.value[1]


# ---------------------------------------------------------------------------
# Q1 机器人自检（题面 Q1·自检状态计算与报告生成）
# ---------------------------------------------------------------------------
def hp_ratio(hp, max_hp):
    """血量百分比，返回 0-100 的 int；计算与边界规则见题面 Q1 规范。"""
    # 整数运算避免浮点精度误差；结果夹回 0-100。
    return max(0, min(100, int(hp) * 100 // int(max_hp)))


def status_report(name, robot_type, hp, max_hp, battery):
    """一行自检报告字符串；档位判定与逐字符格式见题面 Q1 规范。"""
    pct = hp_ratio(hp, max_hp)
    bat = int(battery)  # 截断后的电量读数
    if bat >= 50:
        level = "OK"
    elif bat >= 20:
        level = "WARNING"
    else:
        level = "LOW"
    return "{:<10}|{:^10}|HP {:>3}%|BAT {:>3}%|{}".format(
        name, robot_type, pct, bat, level)


# ---------------------------------------------------------------------------
# Q2 战斗日志分析（题面 Q2·多源日志解析与统计）
# ---------------------------------------------------------------------------
def _parse_sensor_line(text):
    """传感器行 → [(armor, damage), ...]；任一段不合法则整行视为脏行，返回 None。"""
    mapping = {"F": "front", "L": "left", "R": "right"}
    hits = []
    for segment in text.split(","):
        key, sep, value = segment.partition(":")
        if sep != ":" or key not in mapping:
            return None
        if not value.isdigit() or int(value) <= 0:
            return None
        hits.append((mapping[key], int(value)))
    return hits


def _log_line_hits(line, seen_ids):
    """解析一行日志，返回 [(armor, damage), ...]；脏行返回 []。绝不抛异常。

    seen_ids 为带 id 的 JSON 行已计过的 id 集合（原地更新，用于去重）。
    """
    try:
        if not isinstance(line, str):
            return []
        text = line.strip()
        if not text or text.startswith("#"):
            return []
        if text.startswith("{"):
            try:
                record = json.loads(text)
            except ValueError:
                return []
            if not isinstance(record, dict):
                return []
            armor = record.get("armor")
            damage = record.get("damage")
            if armor not in ("front", "left", "right"):
                return []
            if (isinstance(damage, bool) or not isinstance(damage, int)
                    or damage <= 0):
                return []
            if "id" in record:
                rid = record["id"]
                try:
                    if rid in seen_ids:
                        return []
                    seen_ids.add(rid)
                except TypeError:
                    pass  # id 不可哈希：按无 id 的独立事件处理
            return [(armor, damage)]
        hits = _parse_sensor_line(text)
        return hits if hits else []
    except Exception:
        return []


def analyze_damage_log(lines):
    """解析混合格式伤害日志，返回固定契约的统计 dict；
    行格式、去重与统计口径见题面 Q2 规范。"""
    by_armor = {"front": 0, "left": 0, "right": 0}
    total = 0
    events = 0
    seen_ids = set()
    try:
        rows = list(lines)
    except TypeError:
        rows = []
    for line in rows:
        for armor, damage in _log_line_hits(line, seen_ids):
            by_armor[armor] += damage
            total += damage
            events += 1
    most_hit = max(by_armor, key=by_armor.get) if total > 0 else None
    avg = round(total / events, 2) if events else 0.0
    return {"total": total, "by_armor": by_armor,
            "most_hit": most_hit, "avg": avg}


# ---------------------------------------------------------------------------
# Q3 SentryGrid（题面 Q3·载体物理规则）
# ---------------------------------------------------------------------------
class SentryGrid:
    """哨兵仿真载体（构造与只读属性已提供；四个 TODO 方法由你实现）。"""

    def __init__(self, width, height, obstacles, enemy_pos,
                 start_pos=(0, 0), facing=Facing.UP, fuel=100):
        self._width = int(width)
        self._height = int(height)
        if self._width <= 0 or self._height <= 0:
            raise ValueError("地图尺寸必须为正")
        # 障碍坐标存入 set，查询 O(1)——已有实现，勿改。
        self._obstacles = set()
        for ob in obstacles:
            x, y = ob
            self._obstacles.add((int(x), int(y)))
        if not isinstance(enemy_pos, (tuple, list)) or len(enemy_pos) != 2:
            raise TypeError("enemy_pos 需要长度为 2 的 tuple/list")
        self._enemy_pos = self._clamp_cell(enemy_pos)
        if self._enemy_pos in self._obstacles:
            raise ValueError("enemy_pos 不能位于障碍物上")
        if not isinstance(facing, Facing):
            facing = Facing.UP
        self._facing = facing
        self._fuel = int(fuel)
        self._collision_count = 0
        self._pos = self._clamp_cell(start_pos)
        if self._pos in self._obstacles:
            raise ValueError("start_pos 不能位于障碍物上")

    def _clamp_cell(self, cell):
        """已提供：元素转 int 并夹回地图范围（供 __init__ 使用）。"""
        x = int(cell[0])
        y = int(cell[1])
        x = max(0, min(self._width - 1, x))
        y = max(0, min(self._height - 1, y))
        return (x, y)

    # -- 只读属性（已提供，勿改） ------------------------------------------
    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def enemy_pos(self):
        return self._enemy_pos

    @property
    def facing(self):
        return self._facing

    @property
    def fuel(self):
        return self._fuel

    @property
    def collision_count(self):
        return self._collision_count

    @property
    def obstacles(self):
        """障碍集合的只读视图（内部 set 引用，不要修改它）。"""
        return self._obstacles

    @property
    def found_enemy(self):
        return self._pos == self._enemy_pos

    def is_blocked(self, x, y):
        """已提供：坐标是否为障碍或越界（O(1)）。"""
        return ((x, y) in self._obstacles
                or not (0 <= x < self._width and 0 <= y < self._height))

    # -- 你要实现的部分 ------------------------------------------------------
    @property
    def current_pos(self):
        """当前位置 (x, y) 的 tuple。"""
        return self._pos

    @current_pos.setter
    def current_pos(self, value):
        """位置 setter；三重输入校验见题面 Q3 规范第 1 条。

        只接受长度为 2 的 tuple/list（其余抛 TypeError）；
        元素经 _clamp_cell 规范化（转 int 并夹回地图范围）后以 tuple 存储。
        """
        if not isinstance(value, (tuple, list)):
            raise TypeError("current_pos 需要 tuple 或 list")
        if len(value) != 2:
            raise TypeError("current_pos 长度必须为 2")
        self._pos = self._clamp_cell(value)

    def move_forward(self):
        """朝当前 facing 前进一格，返回执行后的位置；
        碰撞、耗电与断电语义见题面 Q3 规范。"""
        if self._fuel <= 0:
            # 底盘断电：前进尝试不产生任何位移，也不判碰撞。
            return self._pos
        dx, dy = self._facing.delta
        nx, ny = self._pos[0] + dx, self._pos[1] + dy
        self._fuel -= 1  # 前进（含碰撞顶墙的尝试）消耗 1 单位电量
        if self.is_blocked(nx, ny):
            # 碰撞：位置不变、朝向不变、碰撞计数 +1。
            self._collision_count += 1
            return self._pos
        self._pos = (nx, ny)
        return self._pos

    def turn_left(self):
        """原地左转 90°，返回新的 Facing（不耗电）。"""
        left_of = {Facing.UP: Facing.LEFT, Facing.LEFT: Facing.DOWN,
                   Facing.DOWN: Facing.RIGHT, Facing.RIGHT: Facing.UP}
        self._facing = left_of[self._facing]
        return self._facing

    def turn_right(self):
        """原地右转 90°，返回新的 Facing（不耗电）。"""
        right_of = {Facing.UP: Facing.RIGHT, Facing.RIGHT: Facing.DOWN,
                    Facing.DOWN: Facing.LEFT, Facing.LEFT: Facing.UP}
        self._facing = right_of[self._facing]
        return self._facing


# ---------------------------------------------------------------------------
# Q4 贪心导航（题面 Q4·单步贪心导航策略）
# ---------------------------------------------------------------------------
def next_step_toward(pos, target, obstacles, current_facing=Facing.UP):
    """返回下一步应朝向的 Facing；
    候选判定、优先级与回退规则见题面 Q4 规范。"""
    px, py = pos[0], pos[1]
    tx, ty = target[0], target[1]
    dist = abs(px - tx) + abs(py - ty)
    dx, dy = tx - px, ty - py
    # 各轴上朝目标的方向（dx/dy 为 0 时该方向的候选判定自然不通过）。
    x_dir = Facing.RIGHT if dx > 0 else Facing.LEFT
    y_dir = Facing.UP if dy > 0 else Facing.DOWN

    blocked = set()
    try:
        blocked = {(ob[0], ob[1]) for ob in obstacles}
    except (TypeError, IndexError, ValueError):
        blocked = set()

    def is_candidate(facing):
        ddx, ddy = facing.delta
        nxt = (px + ddx, py + ddy)
        if nxt in blocked:
            return False
        return (abs(nxt[0] - tx) + abs(nxt[1] - ty)) < dist

    # 平局打破：先走与目标绝对坐标差较大的轴；两轴相等时先走 x 轴。
    prefer_x = abs(dx) >= abs(dy)
    order = (x_dir, y_dir) if prefer_x else (y_dir, x_dir)
    for facing in order:
        if is_candidate(facing):
            return facing
    return current_facing  # 无候选（含已到达/死角）：保持当前朝向


# ---------------------------------------------------------------------------
# Q5 哨兵决策机（题面 Q5·裁判系统决策规则表）
# ---------------------------------------------------------------------------
class SentryState(Enum):
    """哨兵状态机（已提供，勿改）。"""

    PATROL = "PATROL"
    SUSPECT = "SUSPECT"
    ENGAGE = "ENGAGE"
    RETREAT = "RETREAT"
    RETURN = "RETURN"


def decide(sensor, state, hp, heat):
    """纯函数决策，返回 (action: str, new_state: SentryState)；
    sensor 字段契约、R1-R7 规则表与非法输入处理见题面 Q5 规范。"""
    # -- 输入契约校验：契约外输入一律 ValueError ------------------------------
    try:
        frames_raw = sensor["enemy_frames"]
        enemy_dist_raw = sensor["enemy_dist"]
        robot_type_raw = sensor["robot_type"]
        max_hp_raw = sensor["max_hp"]
    except (TypeError, KeyError):
        raise ValueError("sensor 缺少必需字段")
    if not isinstance(frames_raw, (tuple, list)) or not 1 <= len(frames_raw) <= 6:
        raise ValueError("enemy_frames 必须是长度 1-6 的 tuple/list")
    if not isinstance(state, SentryState):
        raise ValueError("state 必须是 SentryState 成员")

    # -- 防御式规范化：字段存在但取值非法不抛异常 ----------------------------
    frames = [bool(f) for f in frames_raw]
    dist = enemy_dist_raw
    if isinstance(dist, bool) or not isinstance(dist, int) or dist < 0:
        dist = None  # 非法敌距（None/负数/非整数）按未知处理
    is_hero = (robot_type_raw == "HERO")  # 未知机型默认按步兵
    try:
        max_hp = int(max_hp_raw)
    except (TypeError, ValueError):
        max_hp = 100
    if max_hp <= 0:
        max_hp = 100
    try:
        hp_pct = hp_ratio(hp, max_hp)
    except (TypeError, ValueError, ZeroDivisionError):
        hp_pct = 0

    # -- 规则术语（基于规范化后的输入）---------------------------------------
    visible = frames[-1]
    confirmed = len(frames) >= 2 and frames[-1] and frames[-2]
    lost_long = len(frames) >= 2 and not frames[-1] and not frames[-2]
    close = dist is not None and dist <= 3

    def engage_action():
        # 敌距 ≤3 开火；否则 HERO 右移、步兵左移（敌距未知按不可开火处理）
        if close:
            return "SHOOT"
        return "MOVE_RIGHT" if is_hero else "MOVE_LEFT"

    # -- R1-R7 固定顺序求值，首条命中即返回 ----------------------------------
    if hp_pct <= 30:  # R1 保命优先（含贴脸交火）
        return ("RETREAT", SentryState.RETREAT)
    if state is SentryState.RETREAT:  # R2 撤退保持（R1 之后 hp_pct 必 > 30）
        if hp_pct > 30:
            return ("RETURN", SentryState.RETURN)
        return ("RETREAT", SentryState.RETREAT)
    if state is SentryState.RETURN:  # R3 返航单帧过渡
        return ("MOVE_BASE", SentryState.PATROL)
    if state is SentryState.ENGAGE:  # R4/R5 交火
        if visible:
            return (engage_action(), SentryState.ENGAGE)
        if lost_long:  # 持续丢失（末两帧均无目标）
            return ("SCAN", SentryState.SUSPECT)
        return ("HOLD_FIRE", SentryState.ENGAGE)  # 短暂丢失
    if state is SentryState.PATROL or state is SentryState.SUSPECT:  # R6/R7
        if visible:
            if confirmed:  # 末两帧均见敌：与 R4 判定一致
                return (engage_action(), SentryState.ENGAGE)
            return ("SCAN", SentryState.SUSPECT)
        if state is SentryState.PATROL:
            return ("PATROL_MOVE", SentryState.PATROL)
        return ("SCAN", SentryState.SUSPECT)
    raise ValueError("无法到达：未知状态 {!r}".format(state))


# ---------------------------------------------------------------------------
# Q6 巡逻任务（题面 Q6·巡逻契约与验收阈值）
# ---------------------------------------------------------------------------
def run_patrol(grid, max_steps=500):
    """sense → decide → act 主循环；
    循环结构、终止条件、脱困自由度与统计返回契约见题面 Q6 规范。

    脱困策略（自定义）：贪心失速（四邻域无严格减距方向）时切入沿墙走——
    默认左手贴墙；绕圈超过 w+h 步换右手；绕圈超过 2*(w+h) 步或重新
    出现减距候选且不比入角时更远，则切回贪心。
    """
    left_of = {Facing.UP: Facing.LEFT, Facing.LEFT: Facing.DOWN,
               Facing.DOWN: Facing.RIGHT, Facing.RIGHT: Facing.UP}
    right_of = {v: k for k, v in left_of.items()}
    rights = {Facing.UP: 0, Facing.RIGHT: 1, Facing.DOWN: 2, Facing.LEFT: 3}
    enemy = grid.enemy_pos

    def manhattan(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def has_candidate():
        pos = grid.current_pos
        dist = manhattan(pos, enemy)
        for f in (Facing.UP, Facing.DOWN, Facing.LEFT, Facing.RIGHT):
            d = f.delta
            nxt = (pos[0] + d[0], pos[1] + d[1])
            if not grid.is_blocked(*nxt) and manhattan(nxt, enemy) < dist:
                return True
        return False

    steps = 0
    visited = {grid.current_pos}
    wall = False
    hand = "L"
    wall_steps = 0
    entry = 0
    limit = grid.width + grid.height

    while (steps < max_steps and grid.fuel > 0
           and not grid.found_enemy):
        pos = grid.current_pos
        if not has_candidate() and not wall:
            wall = True
            hand = "L"
            wall_steps = 0
            entry = manhattan(pos, enemy)
        if wall:
            side = left_of[grid.facing] if hand == "L" else right_of[grid.facing]
            opposite = right_of[grid.facing] if hand == "L" else left_of[grid.facing]

            def cell(f, pos=pos):
                d = f.delta
                return (pos[0] + d[0], pos[1] + d[1])

            if not grid.is_blocked(*cell(side)):
                grid.turn_left() if hand == "L" else grid.turn_right()
            elif grid.is_blocked(*cell(grid.facing)):
                if not grid.is_blocked(*cell(opposite)):
                    grid.turn_right() if hand == "L" else grid.turn_left()
                else:
                    grid.turn_right()
                    grid.turn_right()
        else:
            direction = next_step_toward(grid.current_pos, enemy,
                                         grid.obstacles, grid.facing)
            diff = (rights[direction] - rights[grid.facing]) % 4
            if diff == 3:
                grid.turn_left()
            else:
                for _ in range(diff):
                    grid.turn_right()
        grid.move_forward()
        steps += 1
        visited.add(grid.current_pos)
        if wall:
            wall_steps += 1
            if wall_steps > limit and hand == "L":
                hand = "R"
                wall_steps = 0
            elif wall_steps > 2 * limit:
                wall = False
            elif (has_candidate()
                    and manhattan(grid.current_pos, enemy) < entry + 1):
                wall = False
    return {"steps": steps,
            "collisions": grid.collision_count,
            "visited_count": len(visited),
            "found_enemy": grid.found_enemy,
            "success": grid.found_enemy}


def report_to_json(stats):
    """把 stats 序列化为确定性的 JSON 字符串，见题面 Q6 规范。"""
    return json.dumps(stats, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Bonus：BFS 全局最短路（题面 Bonus·BFS 语义与排行榜）
# ---------------------------------------------------------------------------
def bfs_path_length(start, target, obstacles):
    """BFS 全局最短路步数；返回语义与边界职责见题面 Bonus 规范。

    start == target 返回 0；目标不可达返回 -1。
    obstacles 由调用方负责包含地图边界（否则不可达目标的搜索不会终止）。
    """
    start = (start[0], start[1])
    target = (target[0], target[1])
    if start == target:
        return 0
    blocked = set()
    try:
        blocked = {(ob[0], ob[1]) for ob in obstacles}
    except (TypeError, IndexError, ValueError):
        blocked = set()
    if start in blocked or target in blocked:
        return -1
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        (x, y), dist = queue.popleft()
        for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if nxt == target:
                return dist + 1
            if nxt in blocked or nxt in seen:
                continue
            seen.add(nxt)
            queue.append((nxt, dist + 1))
    return -1  # 队列耗尽：目标不可达


# ---------------------------------------------------------------------------
# 渲染（已提供，demo 专用，不进测试）
# ---------------------------------------------------------------------------
def render_frame(grid, trail=()):
    """ASCII 渲染一帧战场；trail 为走过的格子集合。返回 list[str]。"""
    trail = set(trail)
    rows = []
    for y in range(grid.height - 1, -1, -1):
        row = []
        for x in range(grid.width):
            if (x, y) == grid.current_pos:
                row.append("◉")
            elif (x, y) == grid.enemy_pos:
                row.append("▲")
            elif (x, y) in grid.obstacles:
                row.append("█")
            elif (x, y) in trail:
                row.append("·")
            else:
                row.append(".")
        rows.append("".join(row))
    return rows
