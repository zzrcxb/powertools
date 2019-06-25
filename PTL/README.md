# PTL-2.0

Pythonic Template Language 2.0

## 1. How to use

### 1.1 Arguments

```shell
usage: ptl.py [-h] [-c CODEPAGE] [-i INPUT] [-p] [-o OUTPUT]
              [--context CONTEXT]

optional arguments:
  -h, --help            show this help message and exit
  -c CODEPAGE, --codepage CODEPAGE
                        Set codepage for your input file or strings and
                        communication to python.
  -i INPUT, --input INPUT
                        Set input file name.
  -p, --pipe            Get input from pipe, and it will override -i option
  -o OUTPUT, --output OUTPUT
                        output file name
  --context CONTEXT     Specify context by passing a json string
```

### 1.2 At a Glance

The input template:

```python
# \#include <stdlib.h>

# int main() {
# int array[5] = {1, 2, 3, 4, 5};

import math

for i in range(5):
    # printf("%d", array[{<i>}]);
# # This is a comment
#    double PI = {<math.pi:.4f>};
#    return {<b>};
# }
```

and run:

```shell
python3 ptl.py -i test.c --context "{\"b\":2}"
```

We have these outputs:

```c
#include <stdlib.h>
int main() {
int array[5] = {1, 2, 3, 4, 5};
printf("%d", array[0]);
printf("%d", array[1]);
printf("%d", array[2]);
printf("%d", array[3]);
printf("%d", array[4]);
    double PI = 3.1416;
    return 2;
}
```

Explanations:

```python
# \#include <stdlib.h>  ===> String statement, use "\#" to represent "#" in string statement

# int main() {
# int array[5] = {1, 2, 3, 4, 5};

import math

for i in range(5):   ===> Python code
    # printf("%d", array[{<i>}]);   ===> {<i>} means use variable i's value, and the indentation of first '#' corresponds to the statement indentation in python code. In this case, the "printf" will be duplicated 5 times.
# # This is a comment   ===> Use double ## to make a comment
#    double PI = {<math.pi:.4f>};   ===> Use .4f to format the string
#    return {<b>};
# }
```

**Pay attention!** DO remember to use '\\#' if you want to have '#' in a string.

## 2. Basic Ideas

I want to make PTL as simple as possible and as pythonic as possible. So, I tried to maximize the use of existing python and editors features. The standard procedure of writing a PTL file is following:

- Create a new file and open it with your familiar editor. Change the language to "Python". I recommend you to turn off the real-time linter.

- Write basic control-flow or functions or classes you may use. And use "pass" to create an empty function or loop or branch or class. Which can be reserved for next step. Pay attention to your indentation as your code will be executed by python interpreter finally.

- Replace those "pass"s with your contents. In the above example, it is the C code you want to generate.

- Use your editor shortcut to comment all your contents. For most editors, the shortcut is `Ctrl+/` or `Command+/` for Mac users (Why are you guys using Mac? Why?).

- The indentation of first '#' indicates the scope of this line to help the translator to determine if the line is in a control-flow block or not. For example:

  ```python
  if False:
      # In branch
  # Out of branch
  ```

  will produce:

  ```
  Out of branch
  ```

  But for this one:

  ```python
  if False:
  # In branch
  # Out of branch
  ```

  will produce:

  ```
  In branch
  Out of branch
  ```

- (Optional) If you want to specify the indentation of generated string, please change the amount of whitespaces after the first "#". And the indentation is determined by following formula:

  `indentation = amount of whitespaces // 4` (and your tab will be converted into 4 spaces, bite me!)

  Then, the generated line will have the same indentation as we calculated before. AND it will be 4 SPACES per indentation!

  Or, you may ignore the indentation and format the generated code with other tools (**Recommended**).

- (Optional) Build a dictionary which contains some initial values. (The key must be valid variable names)

So, following the previous steps, the above example is created by these stages:

Build control-flow:

```python
import math

for i in range(5):
    pass
	# This is a comment
```

Add your own contents:

```python
\#include <stdlib.h>

int main() {
int array[5] = {1, 2, 3, 4, 5};

import math

for i in range(5):
    printf("%d", array[{<i>}]);
    # This is a comment
    double PI = {<math.pi:.4f>};
    return {<b>};
}
```

Comment your contents: (`Ctrl+/`)

```python
# \#include <stdlib.h>

# int main() {
# int array[5] = {1, 2, 3, 4, 5};

import math

for i in range(5):
    # printf("%d", array[{<i>}]);
    ## This is a comment
    # double PI = {<math.pi:.4f>};
    # return {<b>};
# }
```

Adjust indentation of first "#":

```python
for i in range(5):
    # printf("%d", array[{<i>}]);
    ## This is a comment
# double PI = {<math.pi:.4f>};
# return {<b>};
```

And it works now!

## 3. Syntax

### 3.1 Statements

- A string statement has the pattern that `([ \t]*)#([^\r\n]+)`. It means before a non-whitespace and a non-# character, it can must have only ONE "#".

  Examples:

  &check;   `# This is a string statement`

  &check;   `# This # is a string statement`

  &check;   `# \#define THIS_IS_A_STRING_STATEMENT`

  &cross;   `This is NOT a string statement`

  **Important**: If your line is started with "#", such as "#include" statement in C. You need to use "\\#" instead or the translator will recognize this line as a comment!

- A comment it similar to string statement, but it requires two "#".

  Examples:

  &check;   `## This is a comment`

  &check;   `#    # This is a comment`

  &cross;   `# This # is not a comment`

- A python statement is a normal python statement which you already know...

### 3.2 Variables

Different from `str.format` in python, the variable is enclosed by '{<' and '>}', rather than '{' and '}'. But, you can still feel free to use those format mini-code such as '4.8f', '0d'. Because '{}' has been used in many languages, it may feel inconvenient to keep write '{{' or '}}' to do the escape.

Examples:

&check;   `{<VAR>}`   This is a variable

&cross;   `{VAR}`    This is NOT a variable

&cross;   `VAR`    This is NOT a variable

During translation, the variables will be searched in **LOCAL SCOPE**. So, please pay attention to your variables scope!





