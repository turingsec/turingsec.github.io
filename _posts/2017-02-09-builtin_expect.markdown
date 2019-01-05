---
layout: post
title:  "__builtin_expect的使用"
date:   2017-02-09 01:48:00
categories: Linux
---

最近研究glibc malloc源码，经常在if语句块中可以看到 __builtin_expect(cond, 0)、__glibc_likely(cond)、__glibc_unlikely(cond)，在源码中可以找到下面宏：

```
#if __GNUC__ >= 3
# define __glibc_unlikely(cond) __builtin_expect ((cond), 0)
# define __glibc_likely(cond) __builtin_expect ((cond), 1)
#else
# define __glibc_unlikely(cond) (cond)
# define __glibc_likely(cond) (cond)
#endif
```

实际上，程序员可以使用likely/unlikely宏来预测cond的结果，然后通知编译器在编译时优化这个分支的汇编代码。
原型: long __builtin_expect (long EXP, long C)，函数返回值就是EXP表达式的值，C是一个常量(0或1)，函数在语义上期待EXP==C，比如下面用法：

```
if (__builtin_expect (x, 0))
foo ();
```

程序员预测x表达式为0，并不希望调用foo()，于是编译器在编译这个if语句块时会调整产生的字节码顺序，使最有可能发生的分支被执行，避免执行jmp指令。现在的CPU都采用流水线技术，流水线其实就是预先加载将要执行但还没执行的字节码，但是如果执行到jmp指令时，就会重新加载接下来的字节码，降低了效率。

从汇编角度观察这些细节，下面源码编译时加入-O2选项：

```
#define likely(x) __builtin_expect(!!(x), 1)
#define unlikely(x) __builtin_expect(!!(x), 0)

int main(char *argv[], int argc)
{
    int a;

    /* Get the value from somewhere GCC can't optimize */
    a = atoi (argv[1]);

    if (unlikely (a == 2))
        a++;
    else
        a--;

    printf ("%d\n", a);

    return 0;
}
```

objdump出汇编代码：

```
080483b0 <main>:
// Prologue
80483b0: push %ebp
80483b1: mov %esp,%ebp
80483b3: push %eax
80483b4: push %eax
80483b5: and $0xfffffff0,%esp
// Call atoi()
80483b8: mov 0x8(%ebp),%eax
80483bb: sub $0x1c,%esp
80483be: mov 0x4(%eax),%ecx
80483c1: push %ecx
80483c2: call 80482e4 <atoi@plt>
80483c7: add $0x10,%esp
80483ca: cmp $0x2,%eax
// --------------------------------------------------------
// 如果a==2(不太可能发生)，那么就执行jmp
// 否则直接执行下面指令，避免了因为jmp指令使流水线重新加载
// --------------------------------------------------------
80483cd: je 80483e1 <main+0x31>
80483cf: dec %eax
// Call printf
80483d0: push %edx
80483d1: push %edx
80483d2: push %eax
80483d3: push $0x80484c8
80483d8: call 80482d4 <printf@plt>
// Return 0
80483dd: xor %eax,%eax
80483df: leave
80483e0: ret
替换源码中unlikely为likely，重新编译，再观察汇编：

080483b0 <main>:
// Prologue
80483b0: push %ebp
80483b1: mov %esp,%ebp
80483b3: push %eax
80483b4: push %eax
80483b5: and $0xfffffff0,%esp
// Call atoi()
80483b8: mov 0x8(%ebp),%eax
80483bb: sub $0x1c,%esp
80483be: mov 0x4(%eax),%ecx
80483c1: push %ecx
80483c2: call 80482e4 <atoi@plt>
80483c7: add $0x10,%esp
80483ca: cmp $0x2,%eax
// --------------------------------------------------
// 如果a==2（很有可能发生），那么就直接执行下面指令，避免了jne跳转
// ---------------------------------------------------
80483cd: jne 80483e2 <main+0x32>
// a++已经在gcc中做了优化
80483cf: mov $0x3,%al
// Call printf()
80483d1: push %edx
80483d2: push %edx
80483d3: push %eax
80483d4: push $0x80484c8
80483d9: call 80482d4 <printf@plt>
// Return 0
80483de: xor %eax,%eax
80483e0: leave
80483e1: ret
```

参考：[FAQ/LikelyUnlikely](http://kernelnewbies.org/FAQ/LikelyUnlikely)