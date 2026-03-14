# `comprehensions` 基准的 Arm vs AMD 深入归因

## 目标

解释这样一种变化：

- 在 CPython 基准分支上，`comprehensions` 的 Arm/AMD 性能比假设约为 `0.8`
- 切换到当前 `cinderx` 分支后，比值进一步下降，例如掉到 `0.6`

这里需要回答的是：

1. 这个 benchmark 真正在跑什么代码
2. `CPython -> CinderX` 后，这些热路径发生了哪些结构性变化
3. 为什么这些变化会对 Arm 比对 AMD/x86_64 更不利

## 1. benchmark 本体到底在测什么

源码在：

- `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_comprehensions/run_benchmark.py`

核心逻辑是构造 `WidgetTray`：

1. 先做一个列表推导，过滤掉 `big spinny` widgets
2. 做一个字典推导，构造 `id_to_widget`
3. 再做一个字典推导，构造 `id_to_derived`
4. 再做一个列表推导，构造用于排序的 tuple
5. 中间还会调用：
   - `_is_big_spinny()`
   - `_any_knobby()`
   - `any(w.has_knob for w in widgets if w)`
6. 属性访问非常密集：
   - `w.kind`
   - `w.has_spinner`
   - `w.widget_id`
   - `w.derived_widget_ids`
   - `w.creator_id`
   - `self.owner_id`
   - `w.has_knob`

所以这不是一个“只测 `LIST_APPEND`”的单 opcode 基准，而是下列热点的组合：

1. list comprehension 的 append
2. dict comprehension 的 setitem
3. dataclass / enum 的属性访问
4. 小函数 / 小方法调用
5. 生成器表达式驱动的 `any()`

## 2. CPython 基准分支上的关键路径

CPython 基准提交 `ebf955df7a89ed0c7968f79faec1de49f61ed7cb` 中，这个 benchmark 最相关的是：

- `/Users/luchen/Repo/cpython/Python/generated_cases.c.h`

### 2.1 comprehension 容器写入

CPython 的热路径比较直接：

1. `LIST_APPEND`
2. `MAP_ADD`
3. `LOAD_ATTR` 专项化变体
4. `CALL` 专项化变体

对 comprehension 来说，最重要的一点是：

- `MAP_ADD` 最终是直接往 `dict` 写
- `LIST_APPEND` 最终是直接往 `list` 追加

也就是说，CPython 的基线设计假设是“普通 list / dict 是默认热路径”。

## 3. CinderX 相对 CPython 的结构变化

`comprehensions` 在 CinderX 上最重要的变化，不是 coroutine 那种 await helper，而是：

1. comprehension 容器写入被泛化成“普通容器或 checked 容器”
2. JIT 也保留了这条泛化路径
3. dataclass 风格属性访问在 JIT 上会多出额外 guard

### 3.1 `MAP_ADD` 被替换成 dict-or-checked-dict helper

在：

- `/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/cinder-bytecodes.c`
- `/Users/luchen/Repo/cinderx/cinderx/StaticPython/checked_dict.c`

CPython 直写 dict 的路径，变成了：

```c
int err = Ci_DictOrChecked_SetItem(dict, key, value);
```

而 `Ci_DictOrChecked_SetItem()` 本身是：

1. 如果 `PyDict_Check(op)`，走 `PyDict_SetItem`
2. 否则如果 `Ci_CheckedDict_Check(op)`，走 `Ci_CheckedDict_SetItem`
3. 否则报错

也就是说，本来在 comprehension 热循环里一次“直接 dict 写入”，变成了一次：

1. 先做普通 dict 检查
2. 再做 checked dict 检查
3. 再分派到真正的 setitem 目标

### 3.2 `LIST_APPEND` 被替换成 list-or-checked-list helper

在：

- `/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/cinder-bytecodes.c`
- `/Users/luchen/Repo/cinderx/cinderx/StaticPython/checked_list.c`

CPython 的 direct list append 被替换成：

```c
int err = Ci_ListOrCheckedList_Append((PyListObject*)list, value);
```

虽然 `Ci_ListOrCheckedList_Append()` 看起来不像 dict helper 那样有显式双分支，但它把普通 list 和 checked list 统一成了一条“通用布局 helper”：

1. `Ci_ListOrCheckedList_GET_SIZE(self)`
2. `list_resize(self, n + 1)`
3. `Py_INCREF(v)`
4. `Ci_ListOrCheckedList_SET_ITEM(self, n, v)`

也就是 comprehension append 在 CinderX 下不再是“沿着 CPython 默认热路径前进”，而是转入 CinderX 自己定义的容器抽象层。

### 3.3 JIT 不会把这条泛化路径抹掉

这点非常重要，因为否则我们只能说“解释器模式变慢”，还解释不了 JIT。

在：

- `/Users/luchen/Repo/cinderx/cinderx/Jit/lir/generator.cpp`

JIT LIR 里：

1. `Opcode::kListAppend` 直接 lowering 到 `Ci_ListOrCheckedList_Append`
2. `Opcode::kSetDictItem` 直接 lowering 到 `Ci_DictOrChecked_SetItem`

也就是说，即使进入 JIT，`comprehensions` 里的 list/dict 写入也没有回到“纯 CPython list/dict 原语”，而是继续走 CinderX 的 generic container helper。

这和 `coroutines` 很像：不是解释器有一套额外逻辑、JIT 就把它优化没了；而是这条逻辑本身已经进入了 JIT 的最终执行形状。

## 4. 静态机器码证据：为什么这对 Arm 更伤

为了不只停留在源码层，我把 `comprehensions` 中最典型的两条 helper 抽成了最小探针，用：

- `aarch64-linux-gnu-gcc 15.2.0`
- `x86_64-linux-gnu-gcc 15.2.0`

交叉编译后做了反汇编。

探针函数：

1. `cpy_map_add`
2. `cx_map_add`
3. `cx_list_append`

### 4.1 `cpy_map_add` vs `cx_map_add`

#### CPython 风格

`cpy_map_add` 的机器码几乎就是“直接跳到 `PyDict_SetItem`”。

在 AArch64 上：

```asm
cpy_map_add:
  b PyDict_SetItem
```

在 x86_64 上：

```asm
cpy_map_add:
  jmp *PyDict_SetItem@GOT
```

这就是最理想的 hot path 形状：没有额外 guard，没有中间分派。

#### CinderX 风格

`cx_map_add` 变成：

1. `PyDict_Check(op)`
2. 如果命中，跳 `PyDict_SetItem`
3. 否则 `Ci_CheckedDict_Check(op)`
4. 如果命中，跳 `Ci_CheckedDict_SetItem`
5. 否则 `PyErr_BadInternalCall`

##### AArch64 形状

关键结构是：

1. `bl PyDict_Check`
2. `cbnz`
3. `bl Ci_CheckedDict_Check`
4. `cbz`
5. 参数寄存器重装
6. `b Ci_CheckedDict_SetItem` 或 `b PyDict_SetItem`

这意味着原来一次 dict 写入，现在先要经过两次 helper 调用和两次分支决策。

##### x86_64 形状

也同样会扩成：

1. `call PyDict_Check`
2. `test/jne`
3. `call Ci_CheckedDict_Check`
4. `test/je`
5. 再 tail jump 到真正目标

但是 x86_64 这串控制流更紧凑，寄存器重装和地址生成都更便宜。

#### 这对 benchmark 的意义

`bm_comprehensions` 里有一个非常热的字典推导：

```python
id_to_widget = {w.widget_id: w for w in widgets}
```

每一次迭代的 `MAP_ADD` 都会走这条路径。  
所以 CinderX 在这里引入的不是一次性的初始化成本，而是**推导循环体里的重复成本**。

### 4.2 `cx_list_append`

`bm_comprehensions` 里也有多个 list comprehension，例如：

```python
widgets = [w for w in widgets if not self._is_big_spinny(w)]
sortable_widgets = [...]
self.sorted_widgets = [id_to_widget[sw[-1]] for sw in sortable_widgets]
```

`cx_list_append` 的探针反汇编显示：

#### AArch64

1. `bl Ci_ListOrCheckedList_GET_SIZE`
2. `add x1, x0, #1`
3. `bl list_resize`
4. `tbnz` 检查失败
5. `bl Py_INCREF`
6. `bl Ci_ListOrCheckedList_SET_ITEM`

#### x86_64

1. `call Ci_ListOrCheckedList_GET_SIZE`
2. `lea`
3. `call list_resize`
4. `test/js`
5. `call Py_INCREF`
6. `call Ci_ListOrCheckedList_SET_ITEM`

这里两边都不轻，但 AArch64 的 helper-call 密度和分支表现更不友好，尤其当这条路径嵌在 comprehension 内循环时。

## 5. 属性访问：为什么 `comprehensions` 不只是容器写入问题

`comprehensions` 里属性访问极多，尤其是 dataclass 样式字段：

1. `w.kind`
2. `w.has_spinner`
3. `w.widget_id`
4. `w.derived_widget_ids`
5. `w.creator_id`
6. `w.has_knob`

对于这类对象，CinderX JIT 会尝试使用：

- `LOAD_ATTR_INSTANCE_VALUE`

但它不是“单纯取字段”，而是会先插入额外的 `inline_values_valid_guard`。

在：

- `/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp`

这条 guard 明确做了：

1. 读取 `tp_basicsize`
2. 计算 `basicsize + offsetof(PyDictValues, valid)`
3. 求出 `valid` 字节地址
4. 读 `valid`
5. 比较 `valid != 0`
6. 再和 type-version guard 组合

### 最小探针的机器码含义

我做了一个缩小版探针：

1. `cpy_attr_slot_guard`：只有 version equality
2. `cx_attr_instance_value_guard`：version equality + `valid` byte 检查

#### AArch64

`cx_attr_instance_value_guard` 的形状是：

1. `ldr obj->ob_type`
2. `ldr tp->tp_basicsize`
3. `ldrb [obj + basicsize]`
4. `cmp valid, 0`
5. `ccmp version, cached`
6. `cset`

#### x86_64

对应是：

1. `mov obj->ob_type`
2. `mov tp->tp_basicsize`
3. `cmpb (%rdi,%rax,1), 0`
4. `setne`
5. `cmp version, cached`
6. `sete`
7. `and`

两边都变复杂了，但 AArch64 仍然更依赖显式加载和地址生成，而 x86_64 在这类 base+index 场景里天然更紧凑。

#### 对 benchmark 的意义

`bm_comprehensions` 不是少量属性访问，而是 comprehension + generator expression + method predicate 中反复访问字段。  
所以即使单次 guard 看起来不夸张，累积起来也会非常可观。

## 6. JIT 侧为什么也会放大 Arm 差距

`comprehensions` 的 JIT 归因可以收束成两条：

1. 容器写入仍走 `Ci_*` helper
2. 属性访问可能生成更重的 guard 链

也就是说，JIT 不是把这些成本“优化掉了”，而是在很多情况下：

1. 把它们保留为 call-heavy helper 路径
2. 或者保留为 guard-heavy field-load 路径

而这两类成本对 AArch64 都更不友好：

1. helper 调用链更容易放大 branch / icache / 参数重装成本
2. guard + 地址计算更容易放大 AArch64 的 addressing-mode 成本

## 7. 为什么平台比值会从 `0.8` 恶化到 `0.6`

现在可以更精确地解释了：

### 在 CPython 基准分支上

`comprehensions` 的核心热路径主要还是：

1. 直接 list append
2. 直接 dict setitem
3. CPython 自带的 attribute specialization

Arm 相比 AMD 已经偏慢，但差距还主要是“同一类原语在不同 ISA 上的基础差异”。

### 切到 CinderX 后

这个 benchmark 的很多热点都被改成了**更泛化**的路径：

1. `MAP_ADD` 变成 `dict-or-checked-dict`
2. `LIST_APPEND` 变成 `list-or-checked-list`
3. JIT 继续沿用这条泛化 helper 路径
4. dataclass 属性访问在 JIT 上带额外 `inline_values_valid_guard`

这些新增成本不是均匀地压到两个平台上：

1. x86_64 也会变慢
2. 但 AArch64 对这类“更多 helper 调用、更多分支、更多地址生成”的新增工作更敏感

因此结果不是“两个平台都同比下降一点”，而是：

- Arm 的相对损失更大
- 所以 Arm/AMD 的性能比进一步恶化

## 8. 当前对 `comprehensions` 的归因结论

按强度排序，`comprehensions` 的平台比值恶化最可能由这 4 层叠加：

1. **comprehension 容器写入被 generic checked-container helper 取代**
   - `Ci_DictOrChecked_SetItem`
   - `Ci_ListOrCheckedList_Append`

2. **JIT 仍然调用这些 helper**
   - `Opcode::kSetDictItem -> Ci_DictOrChecked_SetItem`
   - `Opcode::kListAppend -> Ci_ListOrCheckedList_Append`

3. **dataclass / enum 属性访问很多**
   - benchmark 本身属性读取密度很高

4. **CinderX JIT 的 `LOAD_ATTR_INSTANCE_VALUE` guard 更重**
   - `type-version guard`
   - `inline_values_valid_guard`

## 9. 一句话结论

`comprehensions` 的平台比值变差，不是因为“推导式本身在 Arm 上不好”，而是因为：

**CinderX 把这个 benchmark 最热的 list/dict 写入和部分属性访问，改成了更泛化、更 guard-heavy 的执行路径；这些新增工作在 x86_64 上也有成本，但在 AArch64 上会被放大得更明显，所以 Arm/AMD 的相对比值进一步下降。**
