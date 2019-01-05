---
layout: post
title:  "Linux 用户态下的堆管理"
date:   2016-05-27 08:45:00
categories: Linux
---

## 0x0 序
很早的时候研究过Windows上的堆管理，一直对堆的复杂性充满敬畏。节前看了篇关于Linux堆管理的文章，正好趁着记忆犹新时候写下自己的理解。
附上文章地址：[Understanding glibc malloc](https://sploitfun.wordpress.com/2015/02/10/understanding-glibc-malloc/)

## 0x1 内存分配器
目前市面上有很多的内存分配器

- dlmalloc – General purpose allocator
- ptmalloc2 – glibc
- jemalloc – FreeBSD and Firefox
- tcmalloc – Google
- libumem – Solaris

在Linux早期，dlmalloc曾是Linux下的默认内存分配器，但是随着ptmalloc2对多线程的支持，提高了多线程应用程序的效率，dlmalloc的地位被取代。dlmalloc下，freelist被多个线程共享，当多个线程同时调用malloc，只有一个线程可以进入critical section，造成了效率下降。但是到了ptmalloc2下，每个线程维持一个独立的heap segment，故而这些heap segment的中freelist也是独立的，所以多个线程可以同时调用malloc，提高了效率。对每个线程来说，这种独立的heap segment和freelist就叫做**per thread arena**。

用文章中的例子做个实验，代码如下：

```
/* Per thread arena example. */
#include 
#include 
#include 
#include 
#include <sys/types.h>

void* threadFunc(void* arg)
{
        void *curr_brk;

        curr_brk=sbrk(0);
        printf("Before malloc in thread 1, Program Break Location1:%p\n", curr_brk);
        getchar();
        char* addr = (char*) malloc(1000);
        curr_brk=sbrk(0);
        printf("After malloc and before free in thread 1, Program Break Location:%p\n", curr_brk);
        getchar();
        free(addr);
        curr_brk=sbrk(0);
        printf("After free in thread 1, Program Break Location:%p\n", curr_brk);
        getchar();
}

int main()
{
        pthread_t t1;
        void* s;
        int ret;
        char* addr;
        void *curr_brk;

        curr_brk=sbrk(0); 
        printf("Welcome to per thread arena example::%d\n",getpid());
        printf("Before malloc in main thread, Program Break Location:%p\n", curr_brk);

        getchar();
        addr = (char*) malloc(1000);
        curr_brk=sbrk(0); 
        printf("After malloc and before free in main thread, Program Break Location:%p\n", curr_brk);
        getchar();
        free(addr);
        curr_brk=sbrk(0); 
        printf("After free in main thread, Program Break Location:%p\n", curr_brk);
        getchar();
        ret = pthread_create(&t1, NULL, threadFunc, NULL);
        if(ret)
        {
                printf("Thread creation error\n");
                return -1;
        }
        ret = pthread_join(t1, &s);
        if(ret)
        {
                printf("Thread join error\n");
                return -1;
        }
        return 0;
}
```

分析输出：

```
tyrande000@tyrande000-PC:~/glibc_malloc_test$ ./example
Welcome to per thread arena example::3600
Before malloc in main thread, Program Break Location:0x11ca000
...
tyrande000@tyrande000-PC:~$ cat /proc/3600/maps 
00400000-00401000 r-xp 00000000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
00600000-00601000 r--p 00000000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
00601000-00602000 rw-p 00001000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
...
```

上图可以看出，此时还没有产生heap segment，thread1没创建所以也没有thread1的stack。

```
tyrande000@tyrande000-PC:~//glibc_malloc_test$ ./example 
Welcome to per thread arena example::3600
Before malloc in main thread, Program Break Location:0x11ca000
After malloc and before free in main thread, Program Break Location:0x11eb000
...
tyrande000@tyrande000-PC:~$ cat /proc/3600/maps 
00400000-00401000 r-xp 00000000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
00600000-00601000 r--p 00000000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
00601000-00602000 rw-p 00001000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
011ca000-011eb000 rw-p 00000000 00:00 0 [heap]
...
```

从上图可以看到，heap segment已经产生了，两次输出的program break location表明，该heap segment是由brk() syscall产生。尽管用户只申请了1000字节，但是返回的堆大小是132KB，这一大片连续的内存叫做arena，由于这个arena由主线程创建，又叫做main arena。之后的内存申请将使用这片arena来返回内存块。当没有足够的空间时，这个arena提高program break location来获得更多的空间，实际原理是增加arena的top chunk的大小。相反，当top chunk有足够多的空闲内存，arena也会进行缩小。

```
tyrande000@tyrande000-PC:~/glibc_malloc_test$ ./example
Welcome to per thread arena example::3600
Before malloc in main thread, Program Break Location:0x11ca000
After malloc and before free in main thread, Program Break Location:0x11eb000
After free in main thread, Program Break Location:0x11eb000
...
tyrande000@tyrande000-PC:~$ cat /proc/3600/maps
00400000-00401000 r-xp 00000000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
00600000-00601000 r--p 00000000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
00601000-00602000 rw-p 00001000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
011ca000-011eb000 rw-p 00000000 00:00 0 [heap]
...
```

上图，调用free之后，heap segment并没有立刻释放回操作系统。刚刚那1000字节内存块，由'glibc malloc'库添加到main arena的freelist，freelist在'glibc malloc'库中也称作bin。之后如果用户继续申请内存，'glibc malloc'不再从kernel申请新的内存，而是在bin中寻找符合大小的内存块。只有在没有可用内存块时，才从kernel申请。

```
tyrande000@tyrande000-PC:~/glibc_malloc_test$ ./example
Welcome to per thread arena example::3600
Before malloc in main thread, Program Break Location:0x11ca000
After malloc and before free in main thread, Program Break Location:0x11eb000
After free in main thread, Program Break Location:0x11eb000
Before malloc in thread 1, Program Break Location:0x11eb000
...
tyrande000@tyrande000-PC:~$ cat /proc/3600/maps
00400000-00401000 r-xp 00000000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
00600000-00601000 r--p 00000000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
00601000-00602000 rw-p 00001000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
011ca000-011eb000 rw-p 00000000 00:00 0 [heap]
7f47d72b7000-7f47d72b8000 ---p 00000000 00:00 0
7f47d72b8000-7f47d7ab8000 rw-p 00000000 00:00 0 [stack:3622]
...
```

上图看到，thread1的stack已经产生，但是并没有thread1的heap segment。

```
tyrande000@tyrande000-PC:~/glibc_malloc_test$ ./example
Welcome to per thread arena example::3600
Before malloc in main thread, Program Break Location:0x11ca000
After malloc and before free in main thread, Program Break Location:0x11eb000
After free in main thread, Program Break Location:0x11eb000
Before malloc in thread 1, Program Break Location:0x11eb000
After malloc and before free in thread 1, Program Break Location:0x11eb000
...
tyrande000@tyrande000-PC:~$ cat /proc/3600/maps
00400000-00401000 r-xp 00000000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
00600000-00601000 r--p 00000000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
00601000-00602000 rw-p 00001000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
011ca000-011eb000 rw-p 00000000 00:00 0 [heap]
7f47d0000000-7f47d0021000 rw-p 00000000 00:00 0
7f47d0021000-7f47d4000000 ---p 00000000 00:00 0
7f47d72b7000-7f47d72b8000 ---p 00000000 00:00 0
7f47d72b8000-7f47d7ab8000 rw-p 00000000 00:00 0 [stack:3622]
...
```

观察上图，thread1的heap segment已经创建，并且分布在memory mapping segment，而且program break location并没有改变，说明这块内存是由mmap()创建，并不像主线程中使用brk()。同样的，用户请求1000字节内存，但是kernel映射了64MB(7f47d0000000-7f47d4000000，在那篇文章中32位OS映射了1MB)内存到进程，只有132KB大小内存被设置了read/write属性，成为了thread1可用的堆内存。这连续的132KB内存块**thread arena**。

NOTE:当用户请求的内存大于128字节，并且当前arena没有足够空间，不管请求来自主线程还是工作线程，malloc内部都会调用mmap() syscall。

```
tyrande000@tyrande000-PC:~/glibc_malloc_test$ ./example
Welcome to per thread arena example::3600
Before malloc in main thread, Program Break Location1:0x11ca000
After malloc and before free in main thread, Program Break Location1:0x11eb000
After free in main thread, Program Break Location1:0x11eb000
Before malloc in thread 1, Program Break Location1:0x11eb000
After malloc and before free in thread 1, Program Break Location1:0x11eb000
After free in thread 1, Program Break Location1:0x11eb000
...
tyrande000@tyrande000-PC:~$ cat /proc/3600/maps
00400000-00401000 r-xp 00000000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
00600000-00601000 r--p 00000000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
00601000-00602000 rw-p 00001000 08:02 13115962 /home/tyrande000/glibc_malloc_test/example
011ca000-011eb000 rw-p 00000000 00:00 0 [heap]
7f47d0000000-7f47d0021000 rw-p 00000000 00:00 0
7f47d0021000-7f47d4000000 ---p 00000000 00:00 0
7f47d72b7000-7f47d72b8000 ---p 00000000 00:00 0
7f47d72b8000-7f47d7ab8000 rw-p 00000000 00:00 0 [stack:3622]
...
```

上图，工作线程调用free之后，heap segment同样没有立刻释放回操作系统，而是把刚刚那1000字节由'glibc malloc'库添加到thread arena的bin。

上面的例子，我们看到主线程有main arena，工作线程有thread arena，是否每个线程都有对应的arena呢？当然不是，Linux中存在arena limit的算法，基于CPU核心数

- For 32 bit systems:
     - Number of arena = 2 * number of cores.
- For 64 bit systems:
     - Number of arena = 8 * number of cores.
     
## 0x2 堆数据结构
'glibc malloc'库有3个主要的堆数据结构：
- [heap_info](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/arena.c#L59) - Heap Header - 每个thread arena有多个heap，每个heap有自己的header。初始状态，每个thread arena只有一个heap，随着heap segment没有可用内存，新的heap(和旧heap非连续)由mmap()映射到arena
- [malloc_state](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1671) - Arena Header - 每个Arena只有一个header，包含关于arena的bins, top chunk, last remainder chunk的信息
- [malloc_chunk](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1108) - Chunk Header - 每个heap根据用户请求，被划分为多个chunk，每个chunk都有自己的header。

NOTE:

- main arena只有一个heap，所以没有heap_info数据结构，当arena没有可用内存时，sbrk()函数扩展program break location获得更多内存空间，直到触及Memory Mapping Segment。
- 并不像thread arena，main arena的malloc_state并不是heap segment的一部分，而是一个全局变量，保存在libc.so的data segment
从下图观察main arena和thread arena(single heap segment)


下图thread arena(multiple heap segment)


## 0x3 Chunk的种类
在heap segment中chunk分为以下几种：

- Allocated chunk
- Free chunk
- Top chunk
- Last Remainder chunk

贴一段malloc_chunk的数据结构

```
struct malloc_chunk {

  INTERNAL_SIZE_T      prev_size;  /* Size of previous chunk (if free).  */
  INTERNAL_SIZE_T      size;       /* Size in bytes, including overhead. */

  struct malloc_chunk* fd;         /* double links -- used only if free. */
  struct malloc_chunk* bk;

  /* Only used for large blocks: pointer to next larger size.  */
  struct malloc_chunk* fd_nextsize; /* double links -- used only if free. */
  struct malloc_chunk* bk_nextsize;
};
```

prev_size:如果前一个chunk是空闲状态，那么这个字段保存前一个chunk的大小。如果前一个chunk被分配出去，那么这个字段保存前一个chunk的用户数据
size:用户请求的大小被转换为内部可使用的大小，增加了额外malloc_chunk结构大小，以及内存对齐需要的字节，size保存最终大小。因为最小chunk为16字节并以8递增，[所以低3位不参与size的计算](http://code.woboq.org/userspace/glibc/malloc/malloc.c.html#_M/chunksize)，于是利用低3位保存一些状态信息：

- [PREV_INUSE](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1267) (P) – 第0位：前一个chunk被分配出去时为1
- [IS_MMAPPED](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1274) (M) – 第1位：当此chunk是由mmap()创建则为1
- [NON_MAIN_ARENA](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1283) (N) – 第2位：如果此chunk属于thread arena则为1

下图描述一个被分配出去的chunk：

```
    chunk-> +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	    |             Size of previous chunk                          | |
	    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	    |             Size of chunk, in bytes                       |M|P|
      mem-> +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	    |             User data starts here...                          .
	    .                                                               .
	    .             (malloc_usable_size() bytes)                      .
            .                                                               |
nextchunk-> +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	    |             Size of chunk                                     |
	    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

mem是返回给用户的内存指针，fd,bk,fd_nextsize,bk_nextsize字段在已分配出去的chunk中不使用。

下图描述一个空闲chunk：

```
    chunk-> +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	    |             Size of previous chunk                            |
	    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    `head:' |             Size of chunk, in bytes                         |P|
      mem-> +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	    |             Forward pointer to next chunk in list             |
	    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	    |             Back pointer to previous chunk in list            |
	    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	    |             Unused space (may be 0 bytes long)                .
	    .                                                               .
	    .                                                               |
nextchunk-> +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    `foot:' |             Size of chunk, in bytes                           |
	    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

除了Fast Bin,如果一个chunk处在free状态，那么与它相邻的chunk一定不是free，因为如果都是free，两个chunk就会合并成一个大的chunk。空闲chunk被'glibc malloc'库保存在双向链表中，fd指向同一个bin中的下一个chunk，bk指向同一个bin中的上一个chunk。

## 0x4 Bin的种类
Bin实际上就是保存free chunk的一种数据结构，基于不同大小的chunks，有如下几种bin:

- Fast bin
- Unsorted bin
- Small bin
- Large bin

malloc_state结构中有2个数组分别保存不同的bins：
[fastbinsY](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1680):保存fast bins
[bins](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1689):保存unsorted, small和large bins，数量上一共有126个，划分为：

- Bin 1 – Unsorted bin
- Bin 2 to Bin 63 – Small bin
- Bin 64 to Bin 126 – Large bin

**Fast Bin**:大小在16字节和80字节之间的chunk叫做fast chunk，保存这些fast chunk的bin叫做fast bin，所有种类的bin中，fast bin的效率最高。

- 数量 – [10](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1680)
   - 每个fast bin都是一个单向链表，每个节点都是一个free chunk.之所以采用单向链表这种数据结构，是因为free chunk每次添加或删除都是发生在链表最前端 - LIFO
- chunk大小 – [8 字节递增](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1595)
   - 索引0的fast bin包含的chunk大小为16字节，索引为1的fast bin包含的chunk大小都为24字节，以此列推。
   - 每个fast bin中的chunk大小都相同
- 当 malloc initialization, fast bin中默认最大的chunk为64字节，而不是80字节。
- 不合并 – 两个free状态的chunk可以相互两两毗连，不会合并成一个大的chunk。这种机制可能会造成内存碎片，但是这加快了free效率
- malloc(fast chunk) –
   - 初始状态下fast bin为空，这时用户关于[fast bin](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3330)请求被转换为[small bin](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3367)
   - 当fast bin不为空，根据内部使用的大小（由用户请求转换而来的）[计算](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3332)fast bin的索引，取出链表
   - 将链表第一个chunk[移除](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3341)，并[返回](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3355)给用户
- free(fast chunk) –
   - 根据chunk大小计算合适的fast bin索引，取得链表
   - 将free chunk添加到链表的头部

**Unsorted Bin**:当小chunk或大chunk没有被放回相应的bins时，就会被添加到unsorted bin。这种方法提供了直接使用最近释放内存块的机会，加快了再分配内存的效率，因为省去了分配时寻找相应bins的时间。

- 数量 – 1
   - Unsorted bin 包含一个循环的双向链表
- Chunk大小 – 没有大小限制

**Small Bin**: chunk[小于512字节](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1470)叫做small chunk。保存small chunk的bin叫做small bin。small bin效率介于fast bin和large bin之间

- 数量 – 62
   - 每个small bin都是一个循环双向链表。 small chunk的[unlink](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1411)发生在链表的中间部分，插入操作发生在链表最前端，删除发生在链表的末尾
- Chunk大小 – [8字节递增](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1473)
   - 第一个small bin(bin 2)包含的chunk大小为16字节，第二个small bin(bin 3)包含的chunk大小为24字节，以此列推。
   - 每个small bin中的chunk大小都相同
- 合并 – 相邻的两个chunk会合并成为一个新的chunk，合并操作会减少内存碎片，但是降低了free的效率
- malloc(small chunk) –
   - 初始状态下，small bin是空的。这时用户关于[small bin请求](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3367)被转换为[unsorted bin](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3432)
   - 对于第一次malloc调用，[small bin和large bin](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1689)在malloc_state结构中都指向[自身地址](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3372)，以表明为空
   - 当small bin不为空，根据请求大小[计算](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3369)small bin索引，相应双向链表的最后一个chunk被[移除](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3372)并[返回](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3393)给用户。
- free(small chunk) –
   - 当释放chunk时，检查该chunk前后的chunk是否也为空。如果是的话，将前后的某个chunk从相应的链表取出，合并后放入[unsorted bin链表的最前端](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3995)。

**Large Bin**:chunk大于等于512字节叫做large chunk。保存large chunk的bin叫做large bin。large bin效率低于small bin

- 数量 – 63
  - 每个large bin都是一个循环双向链表，添加或移除操作可以发生在链表的任何地方（前、中、后）
  - 63个bins之中:
      - 32 bins 包含以[64字节递增](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1478)的chunks
      - 16 bins包含以[512字节递增](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1479)的chunks
      - 8 bins 包含以[4096字节递增](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1480)的chunks
      - 4 bins 包含以[32768字节递增](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1481)的chunks
      - 2 bins 包含以[262144字节递增](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1482)的chunks
      - 1 bin 包含一个[剩余](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1483)的大小chunk

  - 不像small bin，large bin中的chunks不一定是相同大小。因此按递减的顺序保存在链表中，最大块的chunk保存在链表最前端，最小块保存在最末端
- 合并 – 两个相邻的free chunk会进行合并
- malloc(large chunk) –
   - 初始情况下，全部的large bins都为空，如果用户请求一个large chunk，那么被转换为[next largest bin](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3639)
   - 对于第一次malloc调用，[small bin和large bin](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1689)在malloc_state结构中都[指向自身地址](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3372)，以表明为空
   - 当large bin不为空时，如果最大的large chunk[大于](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3571)用户请求大小，便[从后向前](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3575)遍历链表去寻找一个合适大小的chunk，一旦找到，将chunk一分为二
      - 返回给用户的部分
      - 剩余chunk大小如果不低于16字节，则添加到unsorted bin
   - 如果最大的large chunk并不能满足用户请求，则[扫描](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3648)binmaps来寻找非空的next largest bin。如果[找到](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3682)，则返回给用户。如果没找到，则使用[top chunk](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3653)。
- free(large chunk) – 过程和small chunk相同

**Top Chunk**:在arena最高地址处的chunk叫做[top chunk](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L1683)，它不属于任何bin。用户发起malloc调用，当arena的所有bins中没有[空闲内存块](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3739)时，并且[top chunk大于用户请求内存大小](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3760)，top chunk划分为2块：

- User chunk (用户请求大小)
- Remainder chunk (剩余大小)

[Remainder chunk 变成了新的top](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L3762)，当top chunk小于用户请求大小，top chunk会进行拓展(main arena使用[sbrk()](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L2458)，thread arena使用[mmap()](https://github.com/sploitfun/lsploits/blob/master/glibc/malloc/malloc.c#L2390))

**Last Remainder Chunk**: 最后一次被划分出来的Remainder chunk。连续的对small chunk的请求可能会导致返回的chunk两两相邻，提高了引用的局部性。
在arena中，哪些chunk可以作为last remainder chunk呢？
当一个用户请求一个small chunk，如果没有可用small bin也没有unsorted bin，则利用binmaps来寻找next largest bin。当找到后，chunk一分为二，除了返回给用户的部分，remainder chunk被添加到unsorted bin，同时成为新的last remainder chunk。
此时，当用户随后请求一个small chunk，并且如果last remainder chunk是unsorted bin中唯一的chunk，last remainder chunk一分为二，除了返回给用户的部分，剩下的remainder chunk重新添加到unsorted bin，同时成为新的last remainder chunk。因此，和之前分配出去的chunk在地址上是连续的。

未完待续...