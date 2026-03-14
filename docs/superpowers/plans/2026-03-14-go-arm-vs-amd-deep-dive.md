# `go`：为什么 CinderX 的对象图和属性流量更容易在 Arm 上被放大

## 1. benchmark 本体在做什么

`bm_go` 不是数值内核，而是一个 9x9 围棋盘模拟。  
热点代码集中在：

- `Square.move()`
- `Square.find()`
- `Square.remove()`
- `Board.useful()`
- `Board.move()`
- `EmptySet.random_choice()`
- `ZobristHash.update()/add()/dupe()`

结构特征非常明显：

- 大量对象字段读写
- 频繁的小方法调用
- 列表、set、history 的更新
- 递归/半递归式连通块查找与移除
- 全局状态 `TIMESTAMP`、`MOVES` 的反复访问

这意味着它更接近“对象图遍历 + 状态机 + 属性交通量” benchmark，而不是纯数学 benchmark。

## 2. CPython 基准分支的关键执行链

在基准 CPython 上，`go` 的主要成本来自：

- `LOAD_ATTR` / `STORE_ATTR`
- `LOAD_METHOD` / `CALL_METHOD`
- list/set/history 相关容器操作
- 分支密集的邻居遍历

比如 `Square.move()`、`Square.remove()`、`Board.useful()` 都是典型的：

- 从对象读很多字段
- 做少量逻辑判断
- 再写回对象字段

因此平台比值主要取决于：

- 属性访问是否便宜
- 小 helper 调用是否便宜
- 分支和地址生成是否紧凑

## 3. 切到 CinderX 后，最关键的差异在哪里

### 3.1 属性访问路径更重

`go` 里最密集的是对象字段流量。  
而 CinderX JIT 的 `LOAD_ATTR_INSTANCE_VALUE` 路径相对基准 CPython 风格 guard，多了：

- `tp_basicsize` 读取
- inline values 地址计算
- `valid` 字节检查

这个差异我们已经在 `comprehensions` 和 `richards` 的 reduced probe 里确认过。

### 3.2 小 helper 入口更重

`go` 的很多热点方法都不大：

- `Square.find()`
- `ZobristHash.update()`
- `EmptySet.set()`
- `Board.move()`

它们和 `richards` 一样，对每次方法入口的固定成本非常敏感。  
CinderX 额外的解释器 bookkeeping 在这类 benchmark 上不容易被摊薄。

### 3.3 容器更新并不都是“纯 CPython 原语”

这个 benchmark 虽然不像 `comprehensions` 那样直接命中 `MAP_ADD` / `LIST_APPEND` opcode，
但它依然有大量：

- `list.append`
- `list.pop`
- `set.add`
- `in set`

这些调用本身又是小方法链的一部分。  
在 CinderX 上，JIT 和解释器都更依赖额外 guard 与 runtime glue，因此对象图 benchmark 的固定成本会被放大。

## 4. 静态机器码层面，为什么 Arm 更容易被这些差异放大

这里最重要的静态代码形状差异仍然是两类：

### 4.1 属性 guard 的 AArch64 地址生成更重

`go` 中最热的路径是：

- `square.color`
- `square.reference`
- `square.ledges`
- `board.zobrist`
- `board.emptyset`
- `neighbour_ref.temp_ledges`

对这类字段访问，CinderX 风格 attr guard 在 AArch64 上通常需要更多：

- 地址生成
- 显式 load/store
- 条件检查

而 x86_64 更容易用较紧凑的 base+disp 形式表达。

### 4.2 tiny helper bookkeeping 在 AArch64 上更难藏起来

`Square.find()`、`ZobristHash.update()` 这种方法本体很短。  
只要入口再多一点：

- call count 更新
- adaptive 状态检查
- PEP523 / frame-eval 相关 glue

在 x86_64 上还可能保持比较紧凑；在 AArch64 上更容易变成显式的分支和 load/store 链。

## 5. JIT 侧为什么 `go` 不像 `raytrace` 那样容易吃到大收益

`go` 的热路径不是长时间停留在一条数值循环里，而是频繁在：

- 属性访问
- 小方法调用
- 邻居遍历
- 容器状态更新

之间切换。  
这意味着 JIT 即使参与，也更依赖：

- attr guard 便宜
- helper glue 便宜
- frame/tstate 访问便宜

而不是依赖“把一长串 float 运算全变成 primitive”。

也就是说，`go` 更像是 `richards` 家族，而不是 `raytrace/float` 家族。

## 6. 为什么平台比值会从 CPython 切到 CinderX 后继续恶化

如果基准 CPython 上 Arm/AMD 比值还相对可接受，而切到 CinderX 后进一步下降，那么 `go` 最合理的解释是：

1. benchmark 主要是对象图遍历和属性流量，不是算术吞吐；
2. CinderX 把属性访问和小方法入口都变得更重；
3. AArch64 对这些“短而碎的固定成本”更敏感；
4. x86_64 能更紧凑地承载这些新增 guard/glue；
5. 因此从 CPython 到 CinderX，Arm 的相对损失会大于 AMD/x86_64。

## 7. 结论

`go` 应归入和 `richards`、`deltablue` 相同的高优先级簇：

- 主因不是数值优化缺失
- 主因是对象字段访问、方法调用和状态更新在 CinderX 上更重
- 而这些新增成本在 AArch64 上更容易被放大

如果要解释“为什么性能比从 0.8 掉到 0.6 一类的变化”，`go` 的第一嫌疑不是某个单独 opcode，而是：

- 更重的 attr guard
- 更重的方法入口 bookkeeping
- 更高的对象图遍历固定成本

