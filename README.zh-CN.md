# Dialogue Bridge

**少重新解释，让新对话接住之前磨合出的理解。**

一个 Codex 插件，把有依据、可修订的背景用于新对话，也让已有独立对话交换发现、纠正理解。

[English](README.md) · [安装](#安装到-codex) · [运行示例](#先试一个小例子) · [反馈感受](https://github.com/zhaosknss/codex-dialogue-bridge/issues/new/choose)

## 我们集中解决什么

一个对话记得为什么改过方向，另一个已经试过某条路并发现问题，第三个准备接着做，
却只知道其中一部分。你需要来回搬背景、重新解释，还可能漏掉某个判断形成的原因。

Dialogue Bridge 希望让这些**已经有各自积累的独立对话**，按需找回原话、交换有依据的意见，
重新理解和修订，再各自继续工作。其他对话也能提醒协调者遗漏了什么。
不同项目可以吸收有用发现，同时保留自己的目标。

它可以用于项目交接、产品方向讨论、写作与研究，或从不同角度审查一个问题。
这些用途共用的流程是：

**找回依据 → 对照理解 → 保留修订 → 各自继续。**

## 早期版本，欢迎拿真实问题试试

当前源码增加 alpha.6 本地试用：新聊天里选择 `@Dialogue Bridge`，贴上来源对话链接，
默认就先理解这些背景；也可以补一句这次要重点了解什么。后来发现理解不对，可以继续修订。
下面的公开 alpha.5 安装标签尚不包含这组新功能。

目前已有历史检索、逐字来源核对、共享贡献、修订和收件箱接续。我们已经用两个已有
Codex 对话做过实际交流，把彼此的发现用于具体核对，也由此修复过插件问题。

首次准备、选择对话、邀请参与和返回结果的体验仍在打磨。你可以告诉我们：哪里又得
重复解释、哪段有用背景没被找到、另一个对话有没有带来实际帮助，或者只是哪里感觉别扭。
安装和使用中的卡点也欢迎反馈；一小段感受就有价值。

[分享一次试用或建议](https://github.com/zhaosknss/codex-dialogue-bridge/issues/new/choose)

## 安装到 Codex

需要支持插件 marketplace 命令的本地 Codex、Python 3.11+ 和 Git。
第一次准备依赖需要联网。

```text
codex plugin marketplace add zhaosknss/codex-dialogue-bridge --ref v0.1.0-alpha.5
codex plugin add dialogue-bridge@dialogue-bridge
```

在新对话里说，例如：

> 用 Dialogue Bridge，让这几个已有对话一起复盘目前的理解和遗漏，各自说明哪些发现
> 适合带回自己的任务：〈对话链接〉。

也可以显式使用 `$dialogue-collaborate`。Skill 会处理私有目录、脚本位置和记录格式，
随包准备脚本可以把固定依赖装到项目自己的隔离环境里。

本仓库就是可添加的插件来源。Git 仓库来源的说明见 [OpenAI 插件指南](https://developers.openai.com/plugins/build/plugins)。

## 新对话沿用背景（alpha.6 试用）

在新建的本地 Codex 聊天里，输入 `@` 并选中已安装的 Dialogue Bridge，再附上对话链接：

```text
@Dialogue Bridge
codex://threads/<对话一的 UUID>
codex://threads/<对话二的 UUID>
```

只有链接时，默认先理解，并简要说明接住了哪些背景，等你继续说要做什么。也可以加一句
“重点了解我们怎么选题和改文”或“先了解这些，我想聊一个新方向”。不必先写交接文档、
取背景组名称或输入脚本命令；索引、查找已有背景和保存由 Skill 内部处理。

流程负责取出相关理解和具体例子，必要时回查原话。同一组链接会查找已有背景并补读更新，
也可以直接提已保存的名称。新聊天不必加入旧讨论组，也不用每次都让所有原对话回应。
不同项目保留适用范围，后来的一次纠正不会自动成为永久规则；理解背景不会自行执行旧任务。

首次索引选定对话已保存的用户／AI 文字；之后读取新增轮次，并重查上次最后一轮，
避免漏掉同一轮后补的消息。更早的历史编辑可以主动完整复核。模型负责理解与取舍，
程序负责来源核对、版本和接续；文档不准确时仍能回到原话及实例。

背景保存在用户自己的私有目录，可复制迁移并重新登记名称；不改写原生记忆或项目
指令。随包[接续说明](plugins/dialogue-bridge/skills/dialogue-collaborate/references/continuation.md)
给出完整入口与数据格式；`scripts/context_demo.py --directory <新的私有目录>` 可运行无需
模型的虚构示例。实际是否更能接住意思、减少重复解释，欢迎用日常任务判断。

## 实际怎么交流

- **找回原始依据。** 分页索引选定对话已保存的用户／AI 文字，检索字面词组，再展开原文和邻近消息。
- **交换有来源的意见。** 贡献带作者、适用范围、接收者、核对过的引文和修订关系。
- **允许重新理解。** 保留旧解释，直接引用另一方的新贡献；修订自己的观点，也可以回应和质疑别人。
- **下次从处理位置继续。** 各对话保存自己的收件箱位置，下次读取新增贡献。

原对话可以主动查看同一份共享收件箱。有原对话消息工具的运行环境中，用户要求交流时，
协调者也可以邀请所选原对话回应。更方便的内置唤醒和参与流程，是我们希望继续完善的部分。

哪些内容重要、某个发现如何影响任务，由使用插件的 AI 结合上下文判断；程序负责存取、
来源核对、可见范围和接续。逐字引用便于回查，解释本身仍可以讨论和修正，各方也可以保留分歧。

## 先试一个小例子

从源码目录准备一个私有环境：

```text
git clone https://github.com/zhaosknss/codex-dialogue-bridge.git
cd codex-dialogue-bridge
python plugins/dialogue-bridge/scripts/setup.py --environment ./local-data/bridge-env
```

准备结果会输出环境的 Python 路径。Windows 下可以这样运行示例：

```powershell
./local-data/bridge-env/Scripts/python.exe plugins/dialogue-bridge/scripts/demo.py --directory ./local-data/demo
```

Linux/macOS 的环境解释器位于 `./local-data/bridge-env/bin/python`。
示例使用预写的虚构对话，展示原话检索、另一方回应、保留修订、重复提交及增量续读。
六项检查应全部为 true，结果和数据库留在所选目录，方便直接查看。
它不读取真实聊天或调用模型；再次运行示例时换一个新数据目录。

实际对话继续使用这个环境的 Python，按 [随包准备与使用说明](plugins/dialogue-bridge/skills/dialogue-collaborate/references/setup.md)
创建另一个私有共享目录；无需指向开发者本机的核心源码。
记录格式见 [贡献格式](plugins/dialogue-bridge/skills/dialogue-collaborate/references/record-format.md)。
聊天原文、引用和数据库留在私有数据目录，不进入版本控制。

## 与通用底层的关系

本插件建立在独立开源库 [Agent State Core](https://github.com/zhaosknss/agent-state-core) 上。
底层提供通用状态、带可见范围的记录、来源与历史；Dialogue Bridge 在上面接入 Codex 历史和对话流程。

插件的 [依赖清单](plugins/dialogue-bridge/requirements.txt) 固定核心提交；准备脚本核对安装来源和分页接口。
通用底层还可以与其他模型、记忆、工具和编排组件组合，具体用途由应用选择。

## 还想改进什么，怎样反馈

- 首次准备和选择对话更顺手，让没有原开发环境的人也能开始使用。
- 邀请原对话参与、收集意见、把发现带回任务的过程更自然。
- 理解实际使用中哪些背景有用、哪些被漏掉，以及还需要解释多少次。
- 更多运行环境和平台的试用。当前本地实测使用 Windows／Python 3.13，CI 覆盖其声明的程序检查矩阵。

反馈只需要说：**你想做什么、实际发生了什么、哪里感觉不对。**
愿意补充时，可以加 Codex 版本、系统或一段脱敏摘录，不需要交出完整私人对话。
也欢迎建议与其他开源工具组合的用法。

## 开发与参考

准备好环境后，使用该环境的 Python 运行：

```text
python -B -m unittest discover -s tests -v
```

程序检查使用虚构材料。理解质量、反馈次数和总 Token 成本，希望通过实际试用及同题比较继续了解。

[Maestro](https://github.com/RunMaestro/Maestro)、[Epistemic Protocols](https://github.com/jongwony/epistemic-protocols)
与 [October Bus](https://github.com/october-dev/october-bus) 提供了编排、理解协议和协作传输方面的参考。
具体版本、许可证、实际依赖与参考设计分别记录在 [UPSTREAM.md](UPSTREAM.md)。

欢迎 [参与改进](CONTRIBUTING.md)。变更见 [CHANGELOG.md](CHANGELOG.md)。MIT License。
