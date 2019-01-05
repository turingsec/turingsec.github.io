---
layout: post
title:  "Stagefright Exploit分析"
date:   2015-09-22 12:08:00
categories: Android
---

## 0x0 序
每公布一个重量级的漏洞，总是忍不住去分析一手，今天就来分析一个号称可以Hack近10亿台Android设备的超级漏洞。

先简单说说Stagefright，它是Android下的多媒体框架，主要采用c++开发，在Android 2.0版本的开发时被加入到AOSP（Android开放源代码项目）。部分应用在Android 2.2中，但在Android 2.3以后就作为默认的多媒体引擎。其他平台上，诸如Mac OS X、Windows、Firefox OS，也都有Stagefright的应用。

以色列移动安全公司Zimperium的VP jduck报告了该框架多个整数溢出漏洞，并于去年9月公开了其中CVE-2015-1538 #1的EXP.

![图片1](https://turingsec.github.io/knowledge/posts/)

公布的EXP生成一个mp4文件，找了一篇介绍MP4文件格式的文章：
[http://thompsonng.blogspot.co.id/2010/11/mp4-file-format.html](http://thompsonng.blogspot.co.id/2010/11/mp4-file-format.html)

另一篇jduck于2015 Blackhat上发表的议题
[Stagefright-Scary-Code-In-The-Heart-Of-Android](https://www.blackhat.com/docs/us-15/materials/us-15-Drake-Stagefright-Scary-Code-In-The-Heart-Of-Android.pdf)

[jduck强调](https://github.com/jduck/cve-2015-1538-1)：“这个EXP并不通用，只在Galaxy Nexus上测试通过，并且要求OS版本是Android 4.0.4 ICS，ICS缓解机制增加了weak ASLR，尽管如此，这个EXP本身也因为堆内存布局的多变性而不能100%的触发”.

Stagefright框架执行在mediaserver进程中:

![图片2](https://turingsec.github.io/knowledge/posts/)

mediaserver是一个本地的系统服务，根据/init.rc文件描述，它会随着系统而启动，并在crash之后自动重启：

![图片3](https://turingsec.github.io/knowledge/posts/)

不仅如此，mediaserver还属于多种特权用户组，从Android源码文件android-4.1.2_r1\system\core\include\private\android_filesystem_config.h可以查到这些用户组对应的特权，已经足以让攻击者spy on you.

![图片4](https://turingsec.github.io/knowledge/posts/)

非常遗憾的是，我的测试机Samsung Galaxy Win Duos GT-I8552并没有Android 4.0.4 ICS的ROM，而是Android4.1.2 Jelly Bean，只在理论上存在可利用性。但是这并不妨碍分析这个只需要知道手机号（其实也不必）就可以Hack的超级漏洞。

![图片5](https://turingsec.github.io/knowledge/posts/)

0x1 漏洞细节
GDB果断登场，附加到/system/bin/mediaserver进程，将EXP生成的mp4文件push到Android设备中。用视频播放器打开mp4文件，畸形的mp4文件将$pc寄存器引导至0xfa22af08，内存unaccessible，程序breakdown

![图片6](https://turingsec.github.io/knowledge/posts/)

记录当前寄存器状态

![图片7](https://turingsec.github.io/knowledge/posts/)

观察寄存器$r1的值和$pc相等，很有可能是在SampleTable::setSampleToChunkParams()中执行了blx  r1。
先打印出SampleTable::setSampleToChunkParams的源码以便对照IDA分析：

```
status_t SampleTable::setSampleToChunkParams(
        off64_t data_offset, size_t data_size) {
    if (mSampleToChunkOffset >= 0) {
        return ERROR_MALFORMED;
    }

    mSampleToChunkOffset = data_offset;

    if (data_size < 8) { return ERROR_MALFORMED; } uint8_t header[8]; if (mDataSource->readAt(
                data_offset, header, sizeof(header)) < (ssize_t)sizeof(header)) {
        return ERROR_IO;
    }

    if (U32_AT(header) != 0) {
        // Expected version = 0, flags = 0.
        return ERROR_MALFORMED;
    }

    mNumSampleToChunkOffsets = U32_AT(&header[4]);

    if (data_size < 8 + mNumSampleToChunkOffsets * 12) {
        return ERROR_MALFORMED;
    }

    mSampleToChunkEntries =
        new SampleToChunkEntry[mNumSampleToChunkOffsets];

    for (uint32_t i = 0; i < mNumSampleToChunkOffsets; ++i) { uint8_t buffer[12]; if (mDataSource->readAt(
                    mSampleToChunkOffset + 8 + i * 12, buffer, sizeof(buffer))
                != (ssize_t)sizeof(buffer)) {
            return ERROR_IO;
        }

        CHECK(U32_AT(buffer) >= 1);  // chunk index is 1 based in the spec.

        // We want the chunk index to be 0-based.
        mSampleToChunkEntries[i].startChunk = U32_AT(buffer) - 1;
        mSampleToChunkEntries[i].samplesPerChunk = U32_AT(&buffer[4]);
        mSampleToChunkEntries[i].chunkDesc = U32_AT(&buffer[8]);
    }

    return OK;
}
```

从Android 4.1.2中取回libstagefright.so并扔进IDA，用frame #1的返回地址0x415458be减去libstagefright.so的基址，得到最后一跳的偏移，分析附近汇编代码：

![图片8](https://turingsec.github.io/knowledge/posts/)

分析程序崩溃原因：
首先$r4是指向当前对象SampleTable的指针，从$r4+8处取出mDataSource的指针放入$r0。在0x948ae处，ldr r1, [r0]指令把mDataSource的虚函数表地址放入$r1，随后0x948BA处指令在虚函数表第7个函数地址处取出readAt(off64_t offset, void *data, size_t size)的指针放入$r1，但是此时的$r1的值已经是非法的了。

接着，SampleTable::setSampleToChunkParams函数是用来处理MP4文件格式stsc Box的函数，我打印出stsc Box的内容，并结合该函数的反汇编、源码深入探讨造成$r1非法值的原因。

![图片9](https://turingsec.github.io/knowledge/posts/)
![图片10](https://turingsec.github.io/knowledge/posts/)

$r7指向源码中的header[8]，内容是00 00 00 00 c0 00 00 03。经过U32_AT函数后，$r0=0xc0000003。IDA偏移0x9487A，执行sampleTable->mNumSampleToChunkOffsets=$r0，此时$r0表示stsc Box中有多少个SampleToChunkEntry结构。随后MULS r0, r3，由于r0是32位寄存器，将0xc0000003*0xC后整数上溢，最终$r0的值为0x24，执行0x9487e处指令后$r1=0x2c，与data_size作比较，data_size实际上就是文件偏移0x1ed3c1处的0x00000034再减去8个字节的stsc头部大小，结果等于0x2c，这样一来data_size==$r1。因此，IDA偏移0x94884处的安全检查被MP4文件精心构造的字节骗过，顺理成章的将$r0=0x24传入new函数，随后大小0x24的buffer被存入sampleTable->mSampleToChunkEntries。

之所以$r3=0xc，是因为SampleToChunkEntry结构由3个uint组成。

```
struct SampleToChunkEntry {
    uint32_t startChunk;
    uint32_t samplesPerChunk;
    uint32_t chunkDesc;
};
```

下面说说for循环，由于sampleTable->mNumSampleToChunkOffsets等于0xc0000003，而sampleTable->mSampleToChunkEntries只有0x24字节的空间，最终导致了heap溢出。现在回过头来分析为什么最终$r1寄存器会被变为非法值。

![图片13](https://turingsec.github.io/knowledge/posts/)

IDA中0x94910处是循环的开始，$r7保存循环变量i的值，我输出了heap溢出前几个对象的地址：

![图片14](https://turingsec.github.io/knowledge/posts/)

$r4指向this，也就是SampleTable对象，$r0指向SampleTable->mDataSource。
随着循环变量i的增加，SampleTable->mSampleToChunkEntries[i]超出了原有的0x24大小，由于mSampleToChunkEntries指向地址小于SampleTable地址，溢出后必然将SampleTable地址上的内容覆盖，于是$r4+8不再指向mDataSource，而是MP4的数据，数据可控。然后从这个数据指向的地址取出虚函数表，那么$r1为什么会变为非法值也就很自然了。

注意，上面讨论的内容只是借测试机的Android 4.1.2辅助分析漏洞原因，jduck的EXP并不是通过溢出SampleTable对象来执行的，因为覆盖SampleTable会导致程序breakdown。

## 0x2  jduck的Exploit原理
说说EXP中的利用方法，EXP首先利用heap spray在MP4文件的tx3g Box申请2M内存，然后预测一个在这2M内出现概率较高的地址sp_addr。

![图片15](https://turingsec.github.io/knowledge/posts/)

EXP将stsc Box作为MP4文件的最后一个Box，大小0x1200字节，里面的数据全都是0x41d00010。
尽管循环上限为0xc0000003次，但for循环在读完这0x1200大小的文件内容后，readAt()返回ERROR_IO，函数返回。每次循环读取文件0xc字节，所以可以理解为for循环上限为0x1200/0xc=0x180。在for 0x180次内，如果覆盖了SampleTable或者mDataSource对象内容，那么必然会导致崩溃（上面分析过）。那既然都不能覆盖，怎样可以成功进入到ROP Chain呢？EXP通过覆盖Track对象的sampleTable指针，直到程序执行到Track对象的析构函数来进入到ROP Chain的。

Track结构：

```
struct Track {
    Track *next;
    sp meta;
    uint32_t timescale;
    sp sampleTable;
    bool includes_expensive_metadata;
    bool skipTrack;
};
```

下面这段代码可以解释Track对象和SampleTable对象的关联：

```
case FOURCC('s', 't', 's', 'c'):
{
    status_t err = mLastTrack->sampleTable->setSampleToChunkParams(
            data_offset, chunk_data_size);

    if (err != OK) {
          return err;
    }

    *offset += chunk_size;
    break;
}
```

考虑这样一种堆布局:

![图片18](https://turingsec.github.io/knowledge/posts/)

mSampleToChunkEntries是在SampleTable::setSampleToChunkParams()中new的，如果Track+0xC的地址小于等于mSampleToChunkEntries+0x1200，并且sampleTable+0x8的地址大于mSampleToChunkEntries+0x1200，溢出数据就可以成功覆盖Track->sampleTable指针，同时for循环不会崩溃。EXP利用MP4格式标准的其它Box申请了一些零碎的内存块，在程序执行过程中这些零碎内存块很有可能被free，那么后面申请的内存就有可能出现在低地址。

当SampleTable::setSampleToChunkParams()因ERROR_IO返回后，程序一路执行，直到触发Track的析构：

![图片19](https://turingsec.github.io/knowledge/posts/)

delete语句从汇编看，调用了android::RefBase::decStrong

![图片20](https://turingsec.github.io/knowledge/posts/)

android::RefBase::decStrong汇编:

![图片21](https://turingsec.github.io/knowledge/posts/)

执行到android::RefBase::decStrong，满足下面条件的话，程序就可以顺利进入ROP Chain：

- 上图$r0就是Track->sambleTable，该指针被预测地址覆盖。
- 之前在tx3g Box申请的2M内存某一page出现在预测地址上。

画了张图，还算清楚的描述了每一page的内容，以及ROP Chain的执行过程。

![图片22](https://turingsec.github.io/knowledge/posts/)

## 0x3 总结
Android 4.1.2上，我最多调到了进入decStrong函数，而且概率非常低。但是这个漏洞的利用过程非常具有学习价值，例如Heap Spray、Stack Pivot、bypass NX+ASLR、创造内存间隙等等，对以后的Exploit非常有帮助，所以写下这篇文章，分享给感兴趣的朋友们。

最后附上几个链接：
- [EXP下载地址](https://github.com/jduck/cve-2015-1538-1)
- [SampleTable::setSampleToChunkParams函数实现](https://android.googlesource.com/platform/frameworks/base/+/ics-mr1/media/libstagefright/SampleTable.cpp)