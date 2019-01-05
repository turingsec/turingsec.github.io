---
layout: post
title:  "编译安装Android ICS到Galaxy Nexus"
date:   2015-09-10 22:48:00
categories: Android
---

本篇文章完整记录了一次编译Android ICS 4.0.4并安装到Galaxy Nexus的过程,大致分为以下部分：

- 准备环境
- 下载Android源代码
- 下载JDK
- 下载Galaxy Nexus驱动程序
- 编译源码+解决错误
- 安装操作系统

## 0x0 准备环境

- 操作系统要求是Linux或者Mac OS，编译Gingerbread (2.3.x)以后的版本需要64位，旧版本可以用32位。我的操作系统：Ubuntu 14.04.3 LTS 64位
最少准备150GB的硬盘空间
- Python 2.6 -- 2.7 [下载地址](http://python.org)
- GNU Make 3.81 -- 3.82 [下载地址](http://gnu.org)
- Git 1.7以上 [下载地址](http://git-scm.com)
- Android 2.3-4.4.4需要JDK 6，这里我们下载 [jdk-6u45-linux-x64.bin](http://download.oracle.com/otn/java/jdk/6u45-b06/jdk-6u45-linux-x64.bin)
- 安装14.04必要的软件包，其它操作系统版本请参考[here](http://source.android.com/source/initializing.html)

```
sudo apt-get install git-core gnupg flex bison gperf build-essential \
  zip curl zlib1g-dev gcc-multilib g++-multilib libc6-dev-i386 \
  lib32ncurses5-dev x11proto-core-dev libx11-dev lib32z-dev ccache \
  libgl1-mesa-dev libxml2-utils xsltproc unzip
```

- 创建目录，这步不是必须的，但是方便了下面步骤

```
tyrande000@tyrande000-PC:~$ mkdir Work
tyrande000@tyrande000-PC:~$ mkdir Work/bin
tyrande000@tyrande000-PC:~$ mkdir Work/src
tyrande000@tyrande000-PC:~$ cd Work
```

## 0x1 下载Android源代码
Repo是一个通过封装了git来方便用户下载Android源码的工具
下载Repo：

```
tyrande000@tyrande000-PC:~/Work$ curl https://storage.233.wiki/git-repo-downloads/repo > ./bin/repo
tyrande000@tyrande000-PC:~/Work$ chmod a+x ./bin/repo
```

tyrande000@tyrande000-PC:~/Work$ export PATH=`pwd`/bin:$PATH
下载源码是一个非常耗时的过程，如果断掉了，可以重新repo sync：

```
tyrande000@tyrande000-PC:~/Work$ cd src
tyrande000@tyrande000-PC:~/Work/src$ repo init -u https://android.googlesource.com/platform/manifest -b android-4.0.4_r1.2
tyrande000@tyrande000-PC:~/Work/src$ repo sync
```

repo init时不加-b分支选项，则直接下载master（最新版本），分支代码可以参考[这里](http://source.android.com/source/build-numbers.html#source-code-tags-and-builds)

## 0x2 下载JDK
JDK下载地址0x0节已经给出了，本节要做的就是安装，并添加到PATH

```
tyrande000@tyrande000-PC:~/Work$ sh ./jdk-6u45-linux-x64.bin
tyrande000@tyrande000-PC:~/Work$ export PATH=`pwd`/jdk1.6.0_45/bin:$PATH
```

## 0x3 下载Galaxy Nexus驱动程序
访问[https://developers.google.com/android/nexus/drivers](https://developers.google.com/android/nexus/drivers)，找到属于自己机型的驱动文件，比如说Galaxy Nexus for Android 4.0.4有3个驱动程序，都下载到word/src/目录：

```
tyrande000@tyrande000-PC:~/Work/src$ for i in *.tgz; do tar -xvzf "./$i"; done
tyrande000@tyrande000-PC:~/Work/src$ for i in *.sh; do sh "./$i"; done

tyrande000@tyrande000-PC:~/Work/src$ source build/envsetup.sh
tyrande000@tyrande000-PC:~/Work/src$ make clobber
```

## 0x4 编译源码+解决错误
都准备好后，下面就开始编译源码，我机器上编译了4小时，期间解决了大概10来个编译错误，这些错误Google基本都能找到解决方法，就不贴在这里了，篇幅太大！

```
tyrande000@tyrande000-PC:~/Work/src$ source build/envsetup.sh
tyrande000@tyrande000-PC:~/Work/src$ lunch
tyrande000@tyrande000-PC:~/Work/src$ make -j4
```

## 0x5 安装操作系统
进行到这一节，最少也得3、4个小时，编译成功后的文件列表：

```
tyrande000@tyrande000-PC:~/Work/src/out/target/product/maguro$ ll
total 309020
drwxrwxr-x  9 tyrande000 tyrande000      4096  1月 29 21:12 ./
drwxrwxr-x  4 tyrande000 tyrande000      4096  2月  1 13:59 ../
-rw-rw-r--  1 tyrande000 tyrande000       145  1月 29 18:38 android-info.txt
-rw-r--r--  1 tyrande000 tyrande000   4247552  1月 29 20:12 boot.img
-rw-rw-r--  1 tyrande000 tyrande000     18364  1月 29 21:04 clean_steps.mk
drwxrwxr-x  2 tyrande000 tyrande000      4096  1月 29 18:37 data/
drwxrwxr-x  2 tyrande000 tyrande000      4096  1月 29 19:14 fake_packages/
-rw-rw-r--  1 tyrande000 tyrande000     42598  1月 29 21:12 installed-files.txt
-rw-rw-r--  1 tyrande000 tyrande000   3918936  1月 29 19:01 kernel
drwxrwxr-x 14 tyrande000 tyrande000      4096  1月 29 21:12 obj/
-rw-rw-r--  1 tyrande000 tyrande000       589  1月 29 21:04 previous_build_config.mk
-rw-rw-r--  1 tyrande000 tyrande000    323965  1月 29 20:12 ramdisk.img
-rw-rw-r--  1 tyrande000 tyrande000    662349  1月 29 20:12 ramdisk-recovery.img
drwxrwxr-x  3 tyrande000 tyrande000      4096  1月 29 20:12 recovery/
-rw-r--r--  1 tyrande000 tyrande000   4585472  1月 29 20:12 recovery.img
drwxrwxr-x  9 tyrande000 tyrande000      4096  1月 29 20:11 root/
drwxrwxr-x  5 tyrande000 tyrande000      4096  1月 29 20:09 symbols/
drwxrwxr-x 13 tyrande000 tyrande000      4096  1月 29 20:31 system/
-rw-r--r--  1 tyrande000 tyrande000 161720932  1月 29 21:12 system.img
-rw-r--r--  1 tyrande000 tyrande000 140856312  1月 29 20:12 userdata.img
```

现在把手机通过USB连接到PC上，只需要最后几步就可大功告成：

```
tyrande000@tyrande000-PC:~/Work/src$ export PATH=`pwd`/out/host/linux-x86/bin:$PATH
tyrande000@tyrande000-PC:~/Work/src$ adb reboot bootloader
tyrande000@tyrande000-PC:~/Work/src$ fastboot oem unlock
tyrande000@tyrande000-PC:~/Work/src$ fastboot erase cache
tyrande000@tyrande000-PC:~/Work/src$ fastboot erase userdata
tyrande000@tyrande000-PC:~/Work/src$ export ANDROID_PRODUCT_OUT=`pwd`/out/target/product/maguro
tyrande000@tyrande000-PC:~/Work/src$ fastboot flashall
```

至此，安装完成。

## 0x6 安装官方ROM
可以到[https://developers.google.com/android/nexus/images](https://developers.google.com/android/nexus/images)下载对应机型的官方rom，以"yakju" for Galaxy Nexus "maguro" 4.0.4为例：

```
tyrande000@tyrande000-PC:~/Downloads/yakju-imm76i$ ls
bootloader-maguro-primela03.img  flash-all.sh  flash-base.sh  image-yakju-imm76i.zip  radio-maguro-i9250xxla02.img
tyrande000@tyrande000-PC:~/Downloads/yakju-imm76i$ adb reboot bootloader
tyrande000@tyrande000-PC:~/Downloads/yakju-imm76i$ ./flash-all.sh
```