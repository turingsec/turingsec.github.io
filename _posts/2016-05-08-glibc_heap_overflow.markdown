---
layout: post
title:  "linux堆溢出实例分析"
date:   2016-05-08 09:12:00
categories: Kernel
---

## 0x0 序
本篇文章在《Linux下的堆管理》基础上，分析一个CTF堆溢出题目shellman的利用过程，附上链接地址：

[exp下载](turingsec.github.io/knowledge/posts/glibc_heap_overflow/exp.py)
[shellman下载](turingsec.github.io/knowledge/posts/glibc_heap_overflow/shellman.zip)
[gdb插件peda](https://github.com/longld/peda)

shellman在初始化时调用了alarm(60)，为调试带来点小障碍，在gdb中关闭即可：

```
gdb-peda$ handle SIGALRM print nopass
Signal        Stop      Print   Pass to program Description
SIGALRM       No        Yes     No              Alarm clock
```

## 0x1 漏洞原因
先简单分析一下shellman程序，程序提供了这些功能

```
*** Shellc0de Manager ***
1. List shellc0de
2. New shellc0de
3. Edit shellc0de
4. Delete shellc0de
5. Execute shellc0de
6. Exit
```

在Edit的处理过程中，没有对原来shellcode buffer的长度做检查，导致了堆溢出

![图片1](turingsec.github.io/knowledge/posts/glibc_heap_overflow/图片1.png)
        
## 0x2 利用原理
《Linux下的堆管理》中提到，small chunk和large chunk在free的过程中会查看地址相邻的前后chunk是否是空闲状态，如果是的话会进行unlink操作，合并成一个更大的chunk，减少内存碎片。

```
    /* consolidate backward */
    if (!prev_inuse(p)) {
      prevsize = p->prev_size;
      size += prevsize;
      p = chunk_at_offset(p, -((long) prevsize));
      unlink(av, p, bck, fwd);
    }

    if (nextchunk != av->top) {
      /* get and clear inuse bit */
      nextinuse = inuse_bit_at_offset(nextchunk, nextsize);

      /* consolidate forward */
      if (!nextinuse) {
	unlink(av, nextchunk, bck, fwd);
	size += nextsize;
      } else
	clear_inuse_bit_at_offset(nextchunk, 0);
```

在shellman中，有个全局数组存放和shellcode相关的数据，每个数组元素是一个0x18大小的数据结构：

- shellcode_exist[i]表示当前shellcode是否存在
- shell_size[i]表示当前shellcode长度
- shell_address[i]表示当前shellcode在堆中的地址

也就是说，shell_address是指向第一个创建的shellcode的地址。
假如创建两个shellcode，在堆中的这两个chunk地址连续。然后edit shellcode1，由于edit时没有做长度检查，可以覆盖chunk2的头部0x8字节，使chunk2->size的PREV_IN_USE位等于0，让其误认为chunk1是空闲状态。稍后free(chunk2)时，导致chunk1会执行unlink:

```
/* Take a chunk off a bin list */
#define unlink(AV, P, BK, FD) {                                               \
    FD = P->fd;	//P == &chunk1					              \
    BK = P->bk;								      \
    if (__builtin_expect (FD->bk != P || BK->fd != P, 0))		      \
      malloc_printerr (check_action, "corrupted double-linked list", P, AV);  \
    else {								      \
        FD->bk = BK;							      \
        BK->fd = FD;
      
        //large chunk do something
        //...
    }
}
```

edit shellcode1时, 需要构造chunk1->fd和chunk1->bk使其绕过安全检查，尽管chunk1的地址并不知道，但shell_address上存放的是chunk1的地址：

- chunk1->fd = shell_address - 0x18(bk在chunk中的偏移)
- chunk1->bk = shell_address - 0x10(fd在chunk中的偏移)

安全检查：

- chunk1->fd->bk 展开后：shell_address - 0x18 + 0x18
- chunk1->bk->fd 展开后：shell_address - 0x10 + 0x10

绕过安全检查，得到一次固定地址写入的机会，最终shell_address不再指向chunk1而是shell_address - 0x18。

![图片5](turingsec.github.io/knowledge/posts/glibc_heap_overflow/图片5.png)

shell_address现在指向自身 - 0x18的低地址，那么再次edit shellcode1的话，程序往这个地址写数据，新的数据会再次覆盖shell_address，使其指向任意地址，加上程序拥有list shellcode功能，因此固定地址写入成功转化成了任意地址读写。

## 0x3 配合info leak
观察shellman got表，发现没有system函数

```
tyrande000@tyrande000-PC:~/heap_overflow_exploit$ objdump -R shellman/shellman.b400c663a0ca53f1f6c6fcbf60defa8d 

shellman/shellman.b400c663a0ca53f1f6c6fcbf60defa8d:     file format elf64-x86-64

DYNAMIC RELOCATION RECORDS
OFFSET           TYPE              VALUE 
00000000006015e0 R_X86_64_GLOB_DAT  __gmon_start__
0000000000601680 R_X86_64_COPY     stdout
0000000000601690 R_X86_64_COPY     stdin
0000000000601600 R_X86_64_JUMP_SLOT  free
0000000000601608 R_X86_64_JUMP_SLOT  putchar
0000000000601610 R_X86_64_JUMP_SLOT  puts
0000000000601618 R_X86_64_JUMP_SLOT  printf
0000000000601620 R_X86_64_JUMP_SLOT  alarm
0000000000601628 R_X86_64_JUMP_SLOT  read
0000000000601630 R_X86_64_JUMP_SLOT  __libc_start_main
0000000000601638 R_X86_64_JUMP_SLOT  __gmon_start__
0000000000601640 R_X86_64_JUMP_SLOT  strtol
0000000000601648 R_X86_64_JUMP_SLOT  malloc
0000000000601650 R_X86_64_JUMP_SLOT  setvbuf
```

要做到system('/bin/sh')，还需要一点努力。
由于现在可以任意地址读写，可以利用泄露free函数地址来计算system函数地址。将free在got表的偏移0x601600写入shell_address

![图片6](turingsec.github.io/knowledge/posts/glibc_heap_overflow/图片6.png)

接下来list shellcode，返回的值就是free函数地址。在libc.so.6中查看free的偏移为0x82df0，system的偏移为0x46640，计算system地址：
system地址 = free_address - 0x82df0 + 0x46640。

## 0x4 触发system('/bin/sh')
现在shell_address指向0x601600，可以再次edit shellcode1，将system函数地址覆盖free函数地址，之后任意的free调用都会错误的调用到system函数，并将参数传递给system()：

![图片3](turingsec.github.io/knowledge/posts/glibc_heap_overflow/图片3.png)

成功获得shell：

![图片4](turingsec.github.io/knowledge/posts/glibc_heap_overflow/图片4.png)

0x5 总结
说说EXP的利用流程，分为以下几个步骤：

1. 先申请2块chunk，让chunk2的大小大于0x80，以至于成为一个small chunk，否则不会触发unlink
2. edit chunk1，使chunk1溢出并重写chunk2的header，使chunk1看起来是free状态，并伪造一些free时用到的数据
3. delete chunk2，glibc free函数会调用unlink合并2个相邻的free状态的chunk，造成一次固定地址写入
4. 重新写入chunk1，因为shall man中shell_address保存chunk1的地址，在Step 3中shell_address被改写成指向shell_address-0x18，因此重写chunk1时会再次改写shell_address指向地址，使其指向free在got表的地址
5. 用list shellcode功能得到free函数地址，根据偏移计算system函数地址
6. 将system函数地址覆盖free在got表的地址
7. 此时任何delete调用都会错误调用到system()