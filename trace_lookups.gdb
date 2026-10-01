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
continue
