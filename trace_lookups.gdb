set pagination off
set confirm off
set print thread-events off
set print inferior-events off
handle SIGSEGV nostop noprint pass
handle SIGBUS nostop noprint pass
handle SIGILL nostop noprint pass
handle SIGFPE nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
handle SIGALRM nostop noprint pass
handle SIGIO nostop noprint pass
handle SIGCHLD nostop noprint pass
handle SIGQUIT nostop noprint pass
handle SIGINT nostop noprint pass
handle SIGTERM nostop noprint pass
handle SIG32 nostop noprint pass
handle SIG33 nostop noprint pass
handle SIG34 nostop noprint pass
handle SIG35 nostop noprint pass
handle SIG63 nostop noprint pass
# BigFileFat::GetIndexFromKey (inlined lookup), at 'pop esi': al!=0 => NOT found
dprintf *0x01b32e4f,"L %d %x %x %x\n",$al,$esi,*(unsigned*)($ebp+8),*(unsigned*)($ebp+4)
# MultiSpawnManager_Update (fastcall, ecx=this): state +0xc0, pending spawn requests (+0xb2 & 0x3fff), +0x18c
dprintf *0x005c6d80,"U %x %x %x %x\n",*(unsigned*)($ecx+0xc0),*(unsigned short*)($ecx+0xb2)&0x3fff,*(unsigned*)($ecx+0x18c),*(unsigned*)($ecx+0x1a0)
# Server_GetBestSpawnPoint(a, b, rule, d) and its result (esi = chosen point, 0 = none)
dprintf *0x005c72d0,"S %x %x %x %x\n",*(unsigned*)($esp+4),*(unsigned*)($esp+8),*(unsigned*)($esp+12),*(unsigned*)($esp+16)
dprintf *0x005c73cc,"R %x\n",$esi
continue
