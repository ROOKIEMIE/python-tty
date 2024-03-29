# 阶段记录
## 2024/03/27
为BaseCommand中的校验器CommandValidator添加了一个变量``` enable_undefined_command ```，
用于控制Console级别的校验器是否在用户输入一些非命令时的拦截行为，该变量在BaseCommand构造时将传入Console校验器CommandValidator中，
通过重载BaseCommand的enable_undefined_command方法，修改其返回值为True，即可实现在Console中放行非命令的输入，
以此来拓展Console的可使用范围，现在有此功能之后，就可以实现一些例如Telnet控制台之类的功能了，可以在Console中方便地决定，
当配置命令都不匹配时，是否应该使用系统命令。

同时，为BaseConsole中run方法添加了命令执行状态变量，用以检测输入的命令是否匹配配置的命令，若输入的命令不匹配任何配置的命令，
则会调用cmd_invoke_miss方法，可以通过重载该方法实现在输入的命令不匹配任何配置的命令时的自定义操作，
该方法为普通方法，入参为该不匹配的命令字符串以及其参数，不要求在继承的自定义Console中一定实现，默认的行为是对不匹配的命令不做任何处理和操作。

将clean_console方法改为普通方法，不要求自定义Console一定要实现该方法。

## 2024/03/26
基本上造完了绘制表格的轮子，目前实现的表格可以做到以下几点：
1. 跨平台，支持在Linux/Windows中可以正常使用(未在Windows环境中测试，但理论上是可以运行的，因为没有依赖一些Linux特有的库，只使用了copy标准库)
2. 只能绘制无边框的表格，纵向暂时没有设置分隔线，水平方向只有标题和数据项之间存在分隔线且该线的符号可以自定义
3. 表格整体可以设置缩进
4. 表格可以设置标题，标题也可以设置缩进
5. 目前只实现了左对齐，无论是表头亦或是数据项都是左对齐
6. 创建表格时输入数据，暂时不支持后续添加数据
7. 初始化表格数据时根据表头项数会对输入的数据项数做判断，数据项数小于表头项数时自动补上空项；反之会截去多余的数据项避免报错
由于该表格最初的目的就是做一个静态表格，因此其不具备一些动态表格的能力，目前来看其所实现的能力基本复合使用需求。

通过``` NoneArgumentValidator ```给出了一个无参方法校验器的例子，该例子中，先通过inspect库提供的方法取得了命令执行函数的参数
再通过传入的命令行输入进行判断

## 2024/03/25
为项目添加了第三方库``` tqdm ```用以实现进度条的展示
除此之外，还希望添加对静态表格的功能，尝试了几款用于绘制ASCII表格的第三方库，发现都无法满足现有的要求
现有的对表格的要求：
1. 跨平台，支持在Linux/Windows中可以正常使用
2. 支持无外边框表格，存在内边框，可以自定义内边框符号
3. 表格整体带缩进
4. 支持配置单元格对齐方式

FIXME:
1. 给出校验器校验命令执行函数的实例

## 2024/03/21
如何通过ConsoleFactory将业务核心注入到每个console中？

FIXME:
1. 校验器应与实际应该执行的命令执行函数绑定，这样才能校验出应该输入多少个参数

## 2024/03/19
现阶段发现并需要做出改进的地方：
1. 重新考虑应该通过什么样的方式来实现Console的命令
   - 在现阶段上进行修改，最终需要达到的目的是——将Console注入到Completer以及Validate中。
   - 将单个命令改成使用类来实现，在其中分别注入Console实例。
2. Console的执行逻辑
   - 先初始化Console的属性
   - 将Console传入Commands，将Commands的Completer和Validate初始化
   - Console整合Commands中所有的命令的Completer和Validate完成Console的构造
3. 了解反射调用方法的方式

## 2024/03/12
对于一个Console所需的组件已经确定了下来，一个Console由一个PromptSession和该Console所拥有的Commands组成
对于PromptSession需要配置Message、Style、Completer和Validator
Message指的是该会话开头所展示的HostName
Style指的是HostName中所各部分以及用户输入时的命令行颜色风格
Completer指的是该命令行会话所带有的补全器，该补全器将分为两层，第一层为该命令会话对各命令的智能补全，第二层为各命令中根据命令的功能所定义的补全器
Validator指的是该命令行会话所带有的校验器，用以校验输入是否合法

整体的UI框架目前初步的设想是由一个主Console以及若干个子Console组成，主Console为所有子Console的最底层，子Console之间没有明确的层次结构
对于主Console，其没有Back命令；在子Console中执行Back命令将回退至上一层Console中
在任意Console中执行Quit或者Exit命令都将退出整个UI
上述两个功能由两个异常来实现：
Back命令由异常``` SubConsoleExit ```定义，当Console捕获该异常时将退出当前Console
Quit或Exit命令由异常``` ConsoleExit ```定义，当Console捕获该异常时将检查当前Console是否为主Console，若不是则将该异常向外抛出；若是则退出Console
