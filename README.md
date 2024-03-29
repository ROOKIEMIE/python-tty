# Command Line Framework/TTY Framework

[中文](README_zh.md)

This is a tty framework developed by Python, aiming to simplify complex tty development.

This framework is based on the third-party library PromptTool kit for secondary development, and many of its capabilities rely on this library. As the library gets updated, this framework updates its functional composition accordingly.

## Console Part
The base class for Console is BaseConsole, which is located in the module __init__.py under the package 'consoles'. If you want to implement a custom Console, you must inherit from this base class.

The PromptSession provided by the third-party library PromptTool is the foundation of a Console in this framework. Each Console contains exclusively one PromptSession.

There is no need for manual definition and configuration for PromptSession, most of its code is already implemented in BaseConsole.

BaseConsole is an abstract class, it has two abstract methods-- ``` init_commands ``` and ``` clean_console ```, which must be implemented by the custom Console, especially the ``` init_commands ``` method.

### **init_commands abstract method**

The main purpose of this abstract method is to bind command objects to the Console. By returning Commands objects, the binding of Console and Commands can be realized.

Since most of the work for commands is actually completed in Commands, when implementing init_commands in Console, it only needs to construct and return the Commands instance, passing itself as an argument during construction.

Feeding the instance of itself is for passing interface instances of the business logic. Simply put your interfaces of specific business into Console, you can obtain the interface of the specific business in specific commands via the Console instance passed in.

## Commands Part
This part is a core of the whole TTY framework, because it involves three major parts: binding of command strings and command execution functions, command completers, and command validators.
Given the powerful command validator and command completer provided by the third-party library, our framework does not limit its functions during integration, thus all of its abilities can be used during actual development.

### Decorators and Base Class
In the ``` __init__.py ``` module under the package 'commands', a decorator ``` register_command ``` and a base class ``` BaseCommands ``` that all commands need to inherit from are defined.

The decorator ``` register_command ``` is used to bind specific command strings and some related information, which is encapsulated with the data class CommandInfo.

Attributes encapsulated by the data class ``` CommandInfo ``` are:

1. func_name— The name of the command in use, i.e. what string input in the command would trigger this command.
2. func_description--The description of the command, which is displayed when the user inputs a help command to show each command's functional description.
3. completer--The class variable of command completer.
4. validator--The class variable of command validator.
5. command_alias--The alias of the command, it can be set when we hope the same function can be invoked by multiple command strings.

The above attributes are passed in as parameters of the decorator, and they are scanned when the module is loaded. For each decorator scanned, a CommandInfo data class is encapsulated, and it binds with the current command execution function decorated (adding a command_info attribute to this function), so that the base class can obtain these information during its construction.

The base class ``` BaseCommands ``` is the core of all abilities offered by Commands. All custom Consoles' Commands must inherit from it. It mainly retrieves CommandInfo obtained by decorators during construction, and bind them to three attributes respectively, and inject the Console passed externally into each command's completer and validator:

1. command_funcs dictionary--Storing the mapping from command strings to command execution functions (including mapping from each alias of the command to the command execution function);
2. command_completers dictionary--Storing the mapping from command strings to command completers (including mapping from each alias of the command to the command completer);
3. command_validators dictionary--Storing the mapping from command strings to command validators (including mapping from each alias of the command to the command validator).

After binding the above three attributes, all completers and validators will be consolidated to facilitate the configuration of Console to PromptSession. At this point, the completer and validator are generated based on command_completers dictionary and command_validators dictionary, they can be understood as the Console's dynamic completer and dynamic validator.

Additionally, an important function of the base class ``` BaseCommands ``` is that it can allow commands that are needed in all Consoles to be included, so that these commands can be triggered in any Console.

Both custom completers and validators of all commands are defined by classes, it is recommended to apply a unified command principle for easy debugging. For example, the xxx command's completer is named XxxCompleter; the xxx command's validator is named XxxValidator.

### Completer

Completers defined by users are codified in classes. It can be either an internal class within Commands or defined outside of Commands module. Regardless of how it is defined, there are two things to note:
1. The constructor contains exactly one parameter—console.
2. Regardless of whether this console variable is used or not, it must be stored within an attribute.

Custom completers can inherit from some default completers provided by PromptTool kit, such as: WordCompleter, FuzzyCompleter, and so on.
During actual use, some completers provided by PromptTool kit require parameters during construction. This requirement can be fulfilled by passing these parameters when executing the constructor of the parent. If there are needs beyond what is provided by the completers of PromptTool kit, the ``` get_completions ``` method can be implemented.

### Validator
A general validator ``` GeneralValidator ``` is defined in the __init__.py module under the package 'commands'. Custom validators must inherit from it to become effective.

The constructor of the general validator GeneralValidator has two parameters—console and func.
The console is the command's Console where this validator belongs; the func is the function variable of the command execution function that needs validation.
Subclasses inheriting from this validator only need to add these two parameters as input parameters, so they could be passed in when the base class BaseCommands is constructed.
However, since the general validator GeneralValidator reserves the abstract attribute of base class Validator provided by the original PromptTool kit, the validate method needs to be implemented to allow actual use.

This method is the core of validation process. The document object from the parameter is the entered string.
Since this validator is nested in the dynamic validator of the Commands class, the dynamic validator will call the corresponding command's validator based on the commands in Document's text entered in the Console.
In the process of calling, the string input will cut off the substring of the original command before passing in.
Thus, the strings that are passed in here do not contain any command strings.
Therefore, you do not need to worry about distinguishing command strings in this validation process, just focus on the input logic of the current command.

The func passed from the constructor is the function variable of the command execution function that needs validation, its parameters can be validated through the inspect library.

### Util Part
In order to enhance the capacity of the entire framework, a utils package has been added to the root directory of the framework. This package implements some features that the dependent library PromptTool kit does not provide, such as: table drawing, progress bar display, etc.

The current progress bar display is implemented through the third-party library tqdm, I will not elaborate on the advantages of this library here.

For the table drawing part, a simple static table has been implemented, which has the following features:
1. Cross-platform, supporting normal use in Linux/Windows (not tested in Windows environment, but theoretically it can run because it does not rely on Linux-specific libraries, just the copy standard library).
2. Only borderless tables can be drawn. No vertical partition line is currently set, and only the title and the data item have a partition line between them horizontally, and the symbol for this line can be customized.
3. The table as a whole can be indented.
4. The table can be set with a title, and the title itself can be indented.
5. Currently, only left alignment is implemented, both for headers and data items.
6. When creating a table, input data into it, but further data additions will not be supported in the current implementation.
7. When initializing table data, an evaluation will be made based on the count of the header items. If the number of data items is less than the number of header items, empty items will be automatically filled in; otherwise, extra data items will be removed to avoid errors.