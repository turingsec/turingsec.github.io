---
layout: post
title:  "IIS8 http.sys漏洞深入分析"
date:   2015-05-01 15:28:00
categories: Exploit
---

## 0x0 序
4月的微软补丁日，发布了标记为高危的MS15-034补丁。ms15-034漏洞出在http.sys中，这个文件是iis的一个重要组件，功能和特性对windows来说意义重大。微软公告说这个漏洞是一个可以执行远程代码的漏洞，但是截至目前为止已发布的poc仅仅只能dos掉系统。笔者通过补丁对比，深入分析了http.sys漏洞的工作原理，这几日把分析记录整理了一手，以此成文。

## 0x1 漏洞原理
首先利用补丁对比，发现修复了下面5个函数。

以第一个UlpParseRange函数为例，看看修复了哪些部分。
运气不错，一下就发现了漏洞出现的原因，原来是64位整数相加，导致了STATUS_INTEGER_OVERFLOW。如果在EAX=0xFFFFFFFF，ECX=0xFFFFFFFF的情况下，

经过ADD EAX,1运算后，EAX上溢为0，CF标志=1。ADC ECX, 0执行时，相当于ECX + 0 + CF，导致ECX上溢为0。补丁通过RtlULongLongAdd函数实现了64位无符号数相加，该函数带有安全检查机制，一旦发现相加后的数溢出就会拦截到该错误。尽管这里有一处溢出，但其实这只是整个漏洞利用过程其中的一处BUG，从函数名字来看，补丁修复的是HTTP协议的Range域，下面尝试构造一个简单的POC，来看看程序是如何执行到UlpParseRange函数的。Range域的格式为Range:bytes=begin-end，该域的作用是可以在客户端指定获取服务器文件的某一范围数据，常用于多线程下载。
js执行后，断在了补丁修复处，可以观察寄存器的值。


UlContentRangeHeaderHandler函数是range域的处理函数，我把它逆向了一手，好弄清楚断点触发前range域都经过了哪些处理，由于代码篇幅太长，这里只贴上伪代码。

```
void UlContentRangeHeaderHandler(REQUEST_INFO *request_info, char *request_value, int len)
{

    char *szBytes = "bytes";
    int begin64[2];//低地址存放低32位，高地址存放高32位
    int length64[2];//这两个参数用于保存UlpParseRange解析range域的值

    if(len < sizeof("bytes"))
    {
        return;
    }

    for(int i = 0;i  <  sizeof("bytes");++i)
    {
        if(request_value[i] != szBytes[i])
        {
            return;
        }
    }
    
    //调用UlpParseRange处理bytes后面的begin和end，也就是“0-18446744073709551615”
    UlpParseRange(request_value, len, &begin64, &length64);

    //将begin和length保存到HTTP Request对象的range属性，2个64位数，共16字节
    memcpy(request_info->range, &begin, 0x10);
}
```

UlpParseRange函数作用就是计算begin和end的差值length，同样的，贴上伪代码：

```
int UlpParseRange(char *request_value, int request_len, int *begin64, int *length64)
{
    //UlpParseRangeNumber函数作用是将字符串解析为64位整数,就不贴代码了
    //解析符号“-”前的begin，将结果保存到begin64
    UlpParseRangeNumber(request_value, &request_len, &request_value, begin64);
    ...

    //request_value修正,request_len修正操作
    ...
   
    //解析符号”-”后面的end，将结果保存到
    UlpParseRangeNumber(request_value, &request_len, &request_value, length64);

    //下面开始进行合法性检查
    if((begin64低32位) & (begin64高32位) == 0xFFFFFFFF)
    {
        return error;
    }

    if(begin64高32位 >= length64高32位)
    {
        if(begin64高32位 > length64高32位)
        {
            return error;
        }
        else
        {
            If(begin64低32位 > length64低32位)
            {
                return error;
            }
        }
    }

    mov eax, leng64低32位//0xFFFFFFFF
    mov edi, begin64低32位//0x0
    mov ecx, length64高32位//0xFFFFFFFF
    mov edx, begin64高32位//0x0
    
    sbb eax, edi//补丁修复前
    sbb ecx, edx
    add eax, 1//eax = 0x0，保存请求长度的低32位
    adc ecx, 0//ecx = 0x0，保存请求长度的高32位

    *length_64 = eax;//length64是一个int [2]数组，高地址保存高32位
    *(length_64 + 4) = ecx;
}
```

Add eax, 1是因为比如range:bytes=50-100，那么请求的文件长度为100 - 50 + 1 = 51。

UlpParseRange函数处理完毕后，返回到UlContentRangeHeaderHandler，该函数随后将begin64和length64复制到http request对象，然后返回。很明显，后面肯定有地方要处理begin64和length64，给这两个地址下读写断点，断在了UlAdjustRangesToContentSize
该函数我只反汇编了一小段，仅这一小段已经足够解释漏洞的整个工作流程。这一小段的代码作用是，将UlpParseRange函数得到的length64和请求的文件实际大小进行修正。

```
void UlAdjustRangesToContentSize(REQUEST_INFO *request,int file_low, int file_high)
{
    int begin_low = request->range[0];
    int begin_high = request->range[4];
    int length_low = request->range[8];
    int length_high = request->range[12];

    //file_low为HTTP请求文件长度的低32位
    //file_high为高32位
    if(begin_high >= file_high)
    {
        if(begin_high > file_high)
        {
            return error;
        }
        else
        {
            if(begin_low >= file_low)
            {
                return error;
            }
        }
    }

    Do
    {
        //如果length_low 和 length_high 都等于0xFFFFFFFF，则必修正
        if((length_low & length_high) != 0xFFFFFFFF)
        {
            mov edx, begin_low
            add edx, length_low//此时edx上溢为0
            mov ecx, begin_high
            adc ecx, length_high//此时ecx上溢为0

            mov end_low, edx
            mov end_high, ecx

            if(end_high < file_high)
            {
                //不需要修正
                break;
            }

            if(end_high == file_high)
            {
                if(end_low < file_low)
                {
                    //不需要修正
                    break;
                }
            }
        }
    
        //下面代码进行length修正
        int adjust_length_low = file_low - begin_low;
        int adjust_length_high = file_high - begin_high;
        request->range[8] = file_low - begin_low;
        request->range[12] = file_high - begin_high;
    }while(false);
    ...
}
```

从伪代码可以看出，如果想绕过修正length部分的代码，构造的Range域必须满足以下几个条件：

假设构造的range域格式为：
**Range:bytes=begin-0xFFFFFFFFFFFFFFFF**

1. begin_high < file_high && begin_low < file_low//File是请求的文件长度
2. 0xFFFFFFFFFFFFFFFF - begin + 1 不能等于0xFFFFFFFFFFFFFFFF，故begin 不能等于1，如果begin等于0的话，那么经过UlpParseRange函数后计算的长度也为0，就不会触发后面的内存破坏，所以begin > 1
虚拟机跑的win8 IIS8.0，poc请求的是iisstart.htm，长度为1307，后面发了一个1306过去，服务器直接挂掉了。后面测试只要2 <= begin < 1307，就可以稳定触发BSOD

## 0x3 BSOD触发点
通过dump，可以确定BSOD的代码处。

此刻看函数调用参数

打印出8570e2f2地址上的数据，本次触发BSOD的begin设置为2

IoBuildPartialMdl函数在传递length时传递了一个超大的整数，导致读取数据时CPU产生PAGE_FAULT_IN_NONPAGED_AREA异常，继而BSOD。

## 0x4 总结
微软官方解释该漏洞为可能允许远程代码执行，理论上通过破坏内存确实有点可行性，但需要设法请求更大的文件，而且数据覆盖的目标地址也很难控制，再加上各种保护，实际操作上，利用漏洞来进行任意代码执行是非常困难的。