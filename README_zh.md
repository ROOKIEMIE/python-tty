# 命令行框架/TTY框架

该框架是基于第三方库PromptTool进行二次开发而来的，许多能力都依赖于该库。该框架也会随着该库的更新，对功能组成进行更新。

## Console部分

Console的基类位于consoles包下的__init__.py模块中的BaseConsole，若想要实现自定义Console则必须继承该基类。

基于第三方库PromptTool所提供的PromptSession将作为构成该框架中一个Console的继承，每个Console中有且仅有一个PromptSession。

PromptSession不需要进行手动的定义和配置，其主要代码都已经在BaseConsole中完成了。

BaseConsole是一个抽象类，其有两个抽象方法——``` init_commands ```和``` clean_console ```，这两个抽象方法都需要自定义Console去完成
特别是``` init_commands ```方法。

### **init_commands抽象方法**

该抽象方法最主要的作用是用来绑定命令对象到Console上用的，通过在其中返回Commands对象从而实现Console和Commands的绑定。

由于对于命令的主要工作其实都在Commands中完成了，所在在Console这里的实现中仅仅只需要将该Commands实例构造并返回即可，构造时需将自己传入其中。

传入自身实例的目的是为了传递业务的接口实例，使用时只需将具体业务的实例放置在Console中，
在具体的命令中就可以通过传入的该Console实例取得具体的业务接口。

## Commands部分

该部分是整个TTY框架的一个核心，因为该部分将涉及三大块：命令字符串与命令执行函数的绑定，命令的补全器以及命令的校验器。
依托于第三方库PromptTool所提供的强大的命令补全器和命令校验器，该框架在整合时并未对其的功能做缩限，因此在实际开发时可以使用其全部能力。

### 装饰器和基类

在commands包下的__init__.py模块中定义了一个装饰器``` register_command ```以及一个所有命令都需要继承的基类``` BaseCommands ```

装饰器``` register_command ```的作用时用以绑定具体的命令字符串以及一些相关的信息，这些相关的信息使用的数据类``` CommandInfo ```进行封装

封装在数据类``` CommandInfo ```中的属性有:
1. func_name——命令的使用名字，即在命令中输入什么字符串会触发该命令
2. func_description——命令的描述，用以在用户输入帮助命令后展示各命令的功能描述
3. completer——命令补全器的类变量
4. validator——命令校验器的类变量
5. command_alias——命令的别名，当我们希望同一个功能可以使用多个命令字符串时可以设置

上述的这些属性将通过装饰器的参数传入，在该模块被装载时扫描，每扫描到一个装饰器，装饰器都会封装一个``` CommandInfo ```数据类，
并将其与当前带有该装饰器的命令执行函数进行绑定(为该函数增加一个``` command_info ```属性)，后续基类在构造的时候就可以取得这些信息。

基类``` BaseCommands ```是所有Commands能提供能力的核心，所有的自定义Console的Commands都需要继承该基类才能生效。
该基类主要完成的工作是在构造时将由装饰器取得的CommandInfo取出，并将其分别绑定到到三个属性上，
并将外部传入的Console注入到每个命令的补全器和校验器中：
1. command_funcs字典——用以存储命令字符串到命令执行函数的映射(包括命令的每个别名到命令执行函数)
2. command_completers字典——用以存储命令字符串到命令补全器的映射(包括命令的每个别名到命令补全器)
3. command_validators字典——用以存储命令字符串到命令检验器的映射(包括命令的每个别名到命令检验器)

绑定完上述的三个属性后，将会统合所有的补全器和检验器，以便于Console将其配置到PromptSession中，
所以此时会根据command_completers字典以及command_validators字典生成completer和validator，
这二者可以理解为Console的动态补全器和动态检验器。

除此之外，基类``` BaseCommands ```还有一个重要的作用，
那就是可以将一些需要在所有Console中都可以使用的命令放入其中，这样就可以做到在任何Console中都可以触发这些命令

所有的命令自定义补全器和校验器统一使用类进行定义，建议使用统一的命令的原则，方便后续代码的Debug，
例如，xxx命令的补全器，叫XxxCompleter；xxx命令的校验器，叫XxxValidator

### Completer补全器

自定义的补全器以类的方式定义，可以选择定义在Commands之内使之成为Commands的内部类或是定义在Commands模块外，
无论是以何种方式定义，都需要注意两点：
1. 构造方法有且仅有一个参数——console
2. 无论是否使用该console变量都需要将其使用一个属性存储下来

自定义的补全器可以继承于PromptTool提供的一些默认补全器，比如:WordCompleter、FuzzyCompleter等补全器，
在具体使用时，一些PromptTool提供的补全器的构造需要带参，由于上述的硬性要求，所以可以在执行父类构造时将这些参数传入即可。
对于一些超出PromptTool提供的补全器的功能，可以选择自己实现其中的``` get_completions ```方法。

### Validator校验器

在commands包下的__init__.py模块中定义了一个通用校验器``` GeneralValidator ```，自定义的校验器需继承它方能生效。

通用校验器``` GeneralValidator ```的构造方法有两个参数——console和func，
console代表的该校验器所属的命令作用的Console，
func代表需要进行校验的命令执行函数的函数变量，
继承的子类校验器只需在构造的入参中加入这两个参数，在基类``` BaseCommands ```进行构造时便会将其传入，
通过由于通用校验器``` GeneralValidator ```保留了原PromptTool提供的``` Validator ```校验器基类的抽象属性，
因此需要实现其中的``` validate ```方法方能使用。
该方法就是校验的核心，可以从参数中取得传入的Document对象，
Document对象的text属性就是当前输入的字符串，
由于该校验器被嵌套在Commands类的动态校验器中，动态校验器会根绝Console中输入的Document的text中的命令匹配对应命令的校验器进行调用，
在调用时，会将输入字符串截去原命令的字符串子串再传入，也就是说，传入该处的字符串都是不带有命令字符串本身的，
因此，此时的校验不必再关心去判断命令字符串，只需要专注于当前命令的输入逻辑即可。

从构造方法中传入的func为需要校验的命令执行函数变量，可以通过inspect库校验其参数

## Util部分

为了使整个框架的能力更加强大，在框架的根目录下添加了utils包，其中将会实现一些依赖库PromptTool所不提供的能力
比如：表格的绘制，进度条展示等功能。

目前进度条展示是通过第三方库tqdm实现，该库的有点就不在这里赘述了。

表格部分，目前实现了一个简单的静态表格，该表格有以下特点:
1. 跨平台，支持在Linux/Windows中可以正常使用(未在Windows环境中测试，但理论上是可以运行的，因为没有依赖一些Linux特有的库，只使用了copy标准库)
2. 只能绘制无边框的表格，纵向暂时没有设置分隔线，水平方向只有标题和数据项之间存在分隔线且该线的符号可以自定义
3. 表格整体可以设置缩进
4. 表格可以设置标题，标题也可以设置缩进
5. 目前只实现了左对齐，无论是表头亦或是数据项都是左对齐
6. 创建表格时输入数据，暂时不支持后续添加数据
7. 初始化表格数据时根据表头项数会对输入的数据项数做判断，数据项数小于表头项数时自动补上空项；反之会截去多余的数据项避免报错
