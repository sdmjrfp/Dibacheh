-- برنامهٔ Dibacheh.app: سرور را بدون پنجرهٔ Terminal اجرا می‌کند.
-- کلیک روی آیکون Dock صفحه را دوباره باز می‌کند و Quit سرور را می‌بندد.
-- این فایل با tools/build_app.sh به Dibacheh.app تبدیل می‌شود.

on serverScript()
	set appPath to POSIX path of (path to me)
	if appPath ends with "/" then set appPath to text 1 thru -2 of appPath
	set projectFolder to do shell script "dirname " & quoted form of appPath
	return quoted form of (projectFolder & "/tools/app_server.sh")
end serverScript

on run
	try
		do shell script "/bin/zsh " & serverScript() & " start"
	on error errorText number errorNumber
		if errorNumber is 2 then
			display dialog "برنامه هنوز نصب نشده است. راهنمای نصب در README.md را ببینید." buttons {"باشد"} default button 1
		else if errorNumber is 3 then
			display dialog "برنامهٔ دیگری پورت 5000 را گرفته است. اگر AirPlay Receiver روشن است، آن را در System Settings خاموش کنید." buttons {"باشد"} default button 1
		else
			display dialog "سرور دیباچه اجرا نشد. Dibacheh.app باید داخل پوشهٔ پروژه بماند." buttons {"باشد"} default button 1
		end if
		quit
		return
	end try
	do shell script "/bin/zsh " & serverScript() & " open"
end run

on reopen
	do shell script "/bin/zsh " & serverScript() & " open"
end reopen

on quit
	try
		do shell script "/bin/zsh " & serverScript() & " stop"
	end try
	continue quit
end quit
