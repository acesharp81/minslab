		var ai_ws;
		var ai_txt_flag=0;
		var smi_small_line=0;
		var smi_flag=0;
		var smi_socket;
		var smi_timer=null;
	    var smi_full_line=0;
		var smi_full_timer;
		var smi_full_opt=0;
		var smi_def_video_id='video_01';
		var smi_server_sw='';
		var smi_server_case=0;
		var dp_chg_flag=0;
		var smi_timer_on=null;
		var vod_bon_txt=0;
		var vod_bon_txt_=-1;

		/* ai 자막 업데이트 함수 */
		function ai_smi_init(url){
			ai_ws = new WebSocket(url, 'echo-protocol');
			ai_ws.binaryType = "arraybuffer";
			ai_ws.addEventListener('open', ai_smi_open);
			ai_ws.addEventListener('message', ai_smi_txt);
			ai_ws.addEventListener('close', ai_smi_close);
			ai_ws.addEventListener('error', ai_smi_error);

		}
		function ai_smi_error(e){ console.info('ai txt error..'+e); }
		function ai_smi_close(e){ 
			console.info('ai txt close..'+e); 
			if($('#'+smi_def_video_id).find("#viewSubtit").css("display") != "none"){
				if(smi_timer_on!=null){ clearTimeout(smi_timer_on); }
				smi_timer_on=setTimeout(function(){ console.log('==> smi reconnect close'); smi_on(); },5000);
			}
		}
		function ai_smi_open(){ console.info('ai txt open..'); }

		function ai_smi_txt(e){
			//console.info(e);
			if(typeof e.data == 'string'){
				var msg =JSON.parse(e.data);
				if (msg.segment!= undefined) {
					if(smi_timer_on!=null){ clearTimeout(smi_timer_on); }

					if (msg.transcript.length<1){ return;}
			

					var stxt_area=$('#'+smi_def_video_id);
					var limit_line=6;
					if (smi_small_line>limit_line){
						var rmcnt=0;
						$(".smi_word").each(function() {
							rmcnt++;
							if (rmcnt<2){
								$(this).remove();
							}else{
								return false;
							}
    
						});
						smi_small_line--;
					}
					
					if (msg.transcripts==''){ msg.transcripts='&nbsp;'}

					stxt_area.find('#smiLoading').hide();
					if (msg.transcripts != undefined) {

						stxt_area.find('.smi_word').attr("style","line-height:22px;width:100%;");
						
						var hwacolor='#237c93';
						for (var an=0;an<msg.transcripts.length;an++){
							var mseg=msg.segment;
							var mtxt=msg.transcripts[an][1];
							var mhwa=msg.transcripts[an][0];
							var lmar="";
							var hwach = false;
							var mclass = '';
							try
							{
								mtxt = mtxt.trim();
								if(mtxt.substr(0,1) != '-'){
									hwach = false;
									mclass = '';
								}else{
									hwach = true;
									mtxt = mtxt.replace('-','');
									if(mhwa=='0'){
										mclass = 'mhwa0';
									}else if(mhwa=='1'){
										mclass = 'mhwa1';
									}
								}
							}
							catch (e)
							{
							}
							if (stxt_area.find('.stxt'+msg.segment).html()!=undefined){
								if (stxt_area.find('#segarr_'+mseg+'_'+an).html()!=undefined){
									$('#segarr_'+mseg+'_'+an).html(''+mtxt+'');
								}else{
									$('.stxt'+msg.segment).append('<span id="segarr_'+mseg+'_'+an+'" style="width:100%;display:block;'+lmar+'">'+mtxt+'</span>');
								}
							}else{
								smi_small_line++;
								stxt_area.find('#viewSubtit .incont').append('<p class="smi_word stxt'+msg.segment+'" style="width:100%;display:block;" ><span id="segarr_'+mseg+'_'+an+'" style="width:100%">'+mtxt+'</span> </p>');
							}
							
							if (mhwa=='-1'){
								stxt_area.find('#segarr_'+mseg+'_'+an).attr("style","background:#cfe5f7; color:#0c2b80; width:100%;");
							}else if (mhwa=='0'){
								stxt_area.find('#segarr_'+mseg+'_'+an).attr("style","background-color:none;width:100%;color:#1e1e1e;display:block;padding-left:22px;");
							}else if (mhwa=='1'){
								stxt_area.find('#segarr_'+mseg+'_'+an).attr("style","background-color:none;color:"+hwacolor+";width:100%;display:block;padding-left:22px;");
							}
							if(mclass!=''){
								$('#segarr_'+mseg+'_'+an).removeClass('mhwa0');
								$('#segarr_'+mseg+'_'+an).removeClass('mhwa1');
								if(hwach){
									$('#segarr_'+mseg+'_'+an).addClass(mclass);
								}
							}

							//	console.info("-----> "+mseg+" - "+an+" / "+mhwa+"  /  "+mtxt+" /  "+msg.scd+" /  "+msg.final+' / '+mclass);

							stxt_area.find('.stxt'+msg.segment).attr("style","line-height:22px;width:100%;");
							stxt_area.find('#viewSubtit .incont').stop().animate({scrollTop:stxt_area.find('#viewSubtit .incont')[0].scrollHeight}, 500);
						}
					}else{ // 화자분리 없을 때
						stxt_area.find('.smi_word').attr("style","line-height:22px;padding-left:7px;border-left: 5px solid #505050;");
						stxt_area.find('.smi_word').find('span').attr("style","background-color:none");
						if (stxt_area.find('.stxt'+msg.segment).html()!=undefined){
							$('.stxt'+msg.segment).html('<span>'+msg.transcript+'</span>');
						}else{
							smi_small_line++;
							stxt_area.find('#viewSubtit .incont').append('<p class="smi_word stxt'+msg.segment+'" style="width:100%;" ><span>'+msg.transcript+'</span> </p>');
						}
						stxt_area.find('.stxt'+msg.segment).attr("style","line-height:22px;padding-left:7px;border-left: 5px solid #36a0ff;");
						stxt_area.find('.stxt'+msg.segment).find('span').attr("style","background:rgba(54, 160, 255, 0.2);");
						stxt_area.find('#viewSubtit .incont').stop().animate({scrollTop:stxt_area.find('#viewSubtit .incont')[0].scrollHeight}, 500);
					}
					try{ smi_send(msg); }catch (e){  }
					// console.info(msg);
				}
			}
		}


		/* 전체화면 자막 업데이트 함수 */
		function smi_opt(a){ smi_full_opt=a; }
		function sminull_full(){
				$('#'+smi_def_video_id).find('.text-full').html("");
				smi_full_line=0;
		}
		function showCaption_full(aaa){
			var init_sc=200;
			var ftxt_area=$('#'+smi_def_video_id).find('.text-full');
			if (videojs.players['YoonVideo_01'].isFullscreen_ && smi_full_opt==1) { 
				if (ftxt_area.css('display') == 'none'){
					ftxt_area.show(); 
					ftxt_area.stop().animate({
					  scrollTop: ftxt_area[0].scrollHeight
					}, 0);
					init_sc=0;
				}
			}else{ 
				if (ftxt_area.css('display') == 'block'){
					ftxt_area.hide();
				}
			}	
			if (ai_txt_flag==1){		
					var msg=aaa;
					if (msg.transcript==''){ return;}
					var limit_line=3;
					if (smi_full_line>limit_line){
						var rmcnt=0;
						$(".video_subtitle_full").each(function() {
							rmcnt++;
							if (rmcnt<2){
								$(this).remove();
							}else{
								return false;
							}
						});
						smi_full_line--;
					}
					if (msg.transcripts != undefined) {
						$('#'+smi_def_video_id).find('.video_subtitle_full').attr("style","line-height:32px;padding-left:7px;margin-bottom: 0px;margin-top: 0px;color:#bbbbbb;");
						var hwacolor='#76D3B0';
						for (var an=0;an<msg.transcripts.length;an++){
							var mseg=msg.segment;
							var mtxt=msg.transcripts[an][1];
							var mhwa=msg.transcripts[an][0];
							var hwach = false;
							var mclass = '';

							if (mtxt==''){ mtxt='&nbsp;'}
							try
							{
								mtxt = mtxt.trim();
								if(mtxt.substr(0,1) != '-'){
									hwach = false;
									mclass = '';
								}else{
									hwach = true;
									mtxt = mtxt.replace('-','');
									if(mhwa=='0'){
										mclass = 'mhwa0f';
									}else if(mhwa=='1'){
										mclass = 'mhwa1f';
									}
								}
							}
							catch (e)
							{
							}
							if ($('#'+smi_def_video_id).find('.ftxt'+msg.segment).html()!=undefined){
								if (ftxt_area.find('#fsegarr_'+mseg+'_'+an).html()!=undefined){
									$('#fsegarr_'+mseg+'_'+an).html(''+mtxt+'');
								}else{
									$('.ftxt'+msg.segment).append('<span id="fsegarr_'+mseg+'_'+an+'" style="width:100%;display:block;color:#B9BCBE;">'+mtxt+'</span>');
								}
							}else{
								smi_full_line++;
								ftxt_area.append('<p class="video_subtitle_full ftxt'+msg.segment+'" style="width:100%;" ><span id="fsegarr_'+mseg+'_'+an+'" style="width:100%;display:block;color:#B9BCBE;;">'+mtxt+'</span> </p>');
							}
								
							//console.info("-----> "+mseg+" - "+an+" / "+mhwa+"  /  "+mtxt+" /  "+msg.scd+" /  "+msg.final+' / '+mclass);
							if (mhwa=='-1'){
								ftxt_area.find('#fsegarr_'+mseg+'_'+an).attr("style","background:none;width:100%;display:block;color:#B9BCBE;");
							}else if (mhwa=='0'){
								ftxt_area.find('#fsegarr_'+mseg+'_'+an).attr("style","background-color:none;width:100%;color:#ffffff;display:block;padding-left:32px;");
							}else if (mhwa=='1'){
								ftxt_area.find('#fsegarr_'+mseg+'_'+an).attr("style","background-color:none;color:"+hwacolor+";width:100%;display:block;padding-left:32px;");
							}
							if(mclass!=''){
								$('#fsegarr_'+mseg+'_'+an).removeClass('mhwa0f');
								$('#fsegarr_'+mseg+'_'+an).removeClass('mhwa1f');
								if(hwach){
									$('#fsegarr_'+mseg+'_'+an).addClass(mclass);
								}
							}
							$('#'+smi_def_video_id).find('.ftxt'+msg.segment).attr("style","line-height:32px;padding-left:7px;margin-bottom: 0px;margin-top: 0px;");
							
							ftxt_area.stop().animate({
							  scrollTop: ftxt_area[0].scrollHeight
							}, init_sc);
						}
					}else{
						if (msg.transcript==''){ msg.transcript='&nbsp;'}
						$('#'+smi_def_video_id).find('.video_subtitle_full').attr("style","line-height:32px;padding-left:7px;border-left: 5px solid #505050;margin-bottom: 0px;margin-top: 0px;");

						if ($('#'+smi_def_video_id).find('.ftxt'+msg.segment).html()!=undefined){
							$('.ftxt'+msg.segment).html(msg.transcript);
						}else{
							smi_full_line++;
							ftxt_area.append('<p class="video_subtitle_full ftxt'+msg.segment+'" style="width:100%;" >'+msg.transcript+' </p>');
						}
						$('#'+smi_def_video_id).find('.ftxt'+msg.segment).attr("style","line-height:32px;padding-left:7px;border-left: 5px solid #1c72e3;margin-bottom: 0px;margin-top: 0px;");
						
						ftxt_area.stop().animate({
						  scrollTop: ftxt_area[0].scrollHeight
						}, init_sc);
					}

					
			}else{
					var limit_line=3;
					if (smi_full_line>limit_line){
						var rmcnt=0;
						$(".video_subtitle_full").each(function() {
							rmcnt++;
							if (rmcnt<2){
								$(this).remove();
							}else{
								return false;
							}
						});
						smi_full_line--;
					}

					//var ft_size=34;
					//if($('.text-full').width()<=1024){ft_size=20;}

					ftxt_area.append('<p class="video_subtitle_full" rel="" style="line-height:32px;padding-left:2px;margin-bottom: 0px;margin-top: 0px;" >'+aaa+'</p>');
					smi_full_line++;

					ftxt_area.stop().animate({
					  scrollTop: ftxt_area[0].scrollHeight
					}, init_sc);
					
					if(smi_full_timer!=null){ clearTimeout(smi_full_timer); }
					smi_full_timer=setTimeout(function(){ sminull_full();},10000);
			}
		}
		function smi_send(t){ var tt = setTimeout(function(){showCaption_full(t)},100); }
		/* 전체화면 자막 업데이트 함수 */

		function smi_mode(){
			if($('#'+smi_def_video_id).find("#viewSubtit").css("display") != "none"){
				smi_off();
				$('#'+smi_def_video_id).find('#smi_btn').attr('src',"./images/test_btn_smi.png");
				$('#'+smi_def_video_id).find('#smi_btn').attr('alt',"자막보기"); $('.Subtitle').attr('title',"자막보기");
			}else{
				$('#'+smi_def_video_id).find('#smiLoading').show();
				smi_on(); 
				$('#'+smi_def_video_id).find('#smi_btn').attr('src',"./images/test_btn_smi_off.png");
				$('#'+smi_def_video_id).find('#smi_btn').attr('alt',"자막닫기"); $('.Subtitle').attr('title',"자막닫기");
			}
		}

		function smi_mode_act(v){
			if(v==0){
				smi_off();
				$('#'+smi_def_video_id).find('#smi_btn').attr('src',"./images/test_btn_smi.png");
				$('#'+smi_def_video_id).find('#smi_btn').attr('alt',"자막보기"); $('.Subtitle').attr('title',"자막보기");
			}else{
				$('#'+smi_def_video_id).find('#smiLoading').show();
				smi_on(); 
				$('#'+smi_def_video_id).find('#smi_btn').attr('src',"./images/test_btn_smi_off.png");
				$('#'+smi_def_video_id).find('#smi_btn').attr('alt',"자막닫기"); $('.Subtitle').attr('title',"자막닫기");
			}
		}
	

		function smi_on(){	
			try{ ai_ws.close(); }catch (e){}
			 smi_server_sw=smi_server;
			 
			 if (rtsp_start==1){
				//rtsp 자막.	
				 smi_server_sw=smi_server;
				 smi_server_case=2;
				 console.log( new Date()+" rtsp smi text start ");
			 }else{
				//hls 자막.
				if (ai_txt_flag==1){
					smi_server_sw=smi_server+"/hls";
				}
				 smi_server_case=1;
				 console.log( new Date()+" hls smi text start ");
			 }

			 smi_flag=1;smi_small_line=0;smi_full_line=0;
			 smi_opt(1);
			 
			$('#'+smi_def_video_id).find('#viewSubtit').show();
			$('#'+smi_def_video_id).find('#viewSubtit .incont').html('');
			$('#'+smi_def_video_id).find('#viewSubtit .incont').css("overflow-y","scroll");
			$('#'+smi_def_video_id).find('#viewSubtit .incont').css("height","100%");
			$('#'+smi_def_video_id).find('#viewSubtit .incont').css("padding","0px");
				 
			$('#'+smi_def_video_id).find('.text-full').css("overflow-y","scroll");
			$('#'+smi_def_video_id).find('.text-full').css("text-align","left");
			$('#'+smi_def_video_id).find('.text-full').css("margin","0px");
			$('#'+smi_def_video_id).find('.text-full').css("padding-left","10px");
			$('#'+smi_def_video_id).find('.text-full').html('');
			$('#'+smi_def_video_id).find('.text-full').css("inset","calc(100% - 63px) 0px 0px");

			if(smi_timer_on!=null){ clearTimeout(smi_timer_on); }
			if($('#'+smi_def_video_id).find("#smiLoading").css("display") != "none"){
				console.log('==> smi reconnect func start ');
				smi_timer_on=setTimeout(function(){ console.log('==> smi reconnect'); smi_on(); },10000);
			}

			 if (ai_txt_flag==1){
				 //$('#'+smi_def_video_id).find('.text-full').css("background","red");
				// $('#'+smi_def_video_id).find('#viewSubtit .incont').css("margin","10px");
				 try{ ai_ws.close(); }catch (e){}
				 ai_smi_init(smi_server_sw);
				 return;
			 }
				

			  try{ smi_socket.disconnect(); }catch (e){}
			  $('#'+smi_def_video_id).find('#viewSubtit').show();
			  smi_socket = io(smi_server_sw); //1
			  smi_socket.on('receive message', function(msg){ //3
				  if(smi_timer_on!=null){ clearTimeout(smi_timer_on); }
				  $('#'+smi_def_video_id).find('#smiLoading').hide();
				var tt = setTimeout(function(){showCaption(msg)},20);
				function showCaption(aaa){
					var limit_line=6;
					if (smi_small_line>limit_line){
						var rmcnt=0;
						$(".smi_word").each(function() {
							rmcnt++;
							if (rmcnt<2){
								$(this).remove();
							}else{
								return false;
							}
    
						});
						smi_small_line--;
					}
					$('#'+smi_def_video_id).find('#viewSubtit .incont').append('<p class="smi_word" style="line-height:22px;padding-left:7px;width:100%;" >'+aaa+'</p>');
					smi_small_line++
					var stxt_area=$('#'+smi_def_video_id);
					stxt_area.find('#viewSubtit .incont').stop().animate({scrollTop:stxt_area.find('#viewSubtit .incont')[0].scrollHeight}, 500);
					
					try{ smi_send(aaa); }catch (e){  }
					if(smi_timer!=null){ clearTimeout(smi_timer); }
					smi_timer=setTimeout(function(){ sminull(); },10000);
				}
			  });
			  smi_socket.on('change name', function(name){ $('#name').val(name); });
		}

		function smi_off(){
			  if(smi_timer_on!=null){ clearTimeout(smi_timer_on); }
			  smi_server_case=0;
			  smi_flag=0; smi_opt(0);
			  if (ai_txt_flag==1){
				 try{ ai_ws.close(); }catch (e){}
				 $('#'+smi_def_video_id).find('#viewSubtit').hide();
				 return;
			  }
			  try{ smi_socket.disconnect(); }catch (e){}
			  $('#'+smi_def_video_id).find('#viewSubtit').hide();
			  sminull();
		}

		function sminull(){ $('#'+smi_def_video_id).find('#viewSubtit .incont').html(""); smi_small_line=0; }

		function  setMedia(id,vtype,vsrc,live) { 
				var player_id = id.split('_');
				$( '#'+id ).addClass( 'videobox' );

				this.objMediaParent = $('#mediaBox_'+player_id[1]);
				this.objMediaParent.html("<div style='width:100%;height:0px;background:#000' id='player_install'></div><video  id='YoonVideo_"+player_id[1]+"' disableRemotePlayback disablePictureInPicture intrinsicsize oncontextmenu='return false;' class='video-js vjs-default-skin vjs-big-play-button vjs-big-play-centered' data-setup='{ \"controls\": true }' preload=\"none\" >");
				
				this.id=id; this.vtype=vtype; this.vsrc=vsrc; this.live=live;
				this.player_event =new  initSetEvent(id,vtype,vsrc,live);
				this.player_embed =new  videojs_embed(id,vtype,vsrc,live);
		}

		setMedia.prototype.add = function() { 
				delete player_embed;
				var player_id = this.id.split('_');
				this.objMediaParent.html("<div style='width:100%;height:0px;background:#000' id='player_install'></div><video  id='YoonVideo_"+player_id[1]+"' disableRemotePlayback disablePictureInPicture intrinsicsize oncontextmenu='return false;' class='video-js vjs-default-skin vjs-big-play-button vjs-big-play-centered' data-setup='{ \"controls\": true }' preload=\"none\" >");
				this.player_embed =new  videojs_embed(this.id,this.vtype,this.vsrc,this.live);
		
		}

		var initSetEvent = function(id,vtype,vsrc,live) {
			var player_id = id;
			var player_id_ = id.split('_');
			var main_audio = 0;
			var main_zoom = 0;

			if (document.body.offsetWidth>850){
					main_zoom=0;
					$($('#'+id).find('.ZoomSmall')).find('img').attr("src","./images/test_btn_small.png");
					$($('#'+id).find('.ZoomWide')).find('img').attr("src","./images/test_btn_wide.png");
			}
			if (player_id_[1]=='01' ){ resizeVideoJS(player_id_[1]);}
			

			// 오디오듣기, 영상보기 등 컨트롤
			$('#'+id).find(".AudioHearing").click(function(id) {
				$(this).removeClass('on');
				$('#'+player_id).find('.audioimg').attr('src','./images/img_view.jpg');
				if (main_audio==0){ 
					$(this).attr('title','오디오만듣기 끄기');
					$(this).addClass('on'); main_audio=1; $('#'+player_id).find('.vjs-poster').attr('rel','1'); $('#'+player_id).find('.vjs-poster').show(); }else{
					main_audio=0;
					$(this).attr('title','오디오만듣기 켜기');
					$('#'+player_id).find('.vjs-poster').attr('rel','0');
					$('#'+player_id).find('.audioimg').attr('src','./images/bg_webcast.png?260731');
					if ($('#'+player_id).find('.vjs-big-play-button:button').css('display') === 'none' ) {
						$('#'+player_id).find('.vjs-poster').hide();
					}
				}
			});


			// 작은화면
			$('#'+id).find(".btn_small").click(function() {
				if (id=='video_01'){setCookiepop('player_opt','-1',1);}
			
				if (id=='video_01' && !$('#video_01').find(".btn_small").hasClass("on")){
						$('#video_01').find(".btn_small").attr('title','작은화면 끄기');
				}
				if (id=='video_01' && $('#video_01').find(".btn_small").hasClass("on")){
					$(this).attr('title','작은화면 켜기');
					setCookiepop('player_opt','0',1)
				}
				  $(".player_box").removeClass("size_wide");
				  $(".player_box").toggleClass("size_small");
				  $('#video_01').find(".btn_wide").removeClass("on");
				  $('#video_01').find(".btn_small").toggleClass("on");
				  resizeVideoJS('');
				 if ($('#video_01').find(".btn_small").hasClass("on")){
					$('#video_02').find(".btn_wide").removeClass("on").addClass("on");
					$('#video_03').find(".btn_wide").removeClass("on").addClass("on");
				 }
				 if ($('#video_01').find(".btn_wide").hasClass("on")){
					$('#video_02').find(".btn_wide").removeClass("on");
					$('#video_03').find(".btn_wide").removeClass("on");
				 }
				 if (!$('#video_01').find(".btn_wide").hasClass("on") && !$('#video_01').find(".btn_small").hasClass("on")){
					$('#video_02').find(".btn_wide").removeClass("on");
					$('#video_03').find(".btn_wide").removeClass("on");
				 }
				 

			});

			// 넓은화면
			$('#'+id).find(".btn_wide").click(function() {
				if (id=='video_01'){ setCookiepop('player_opt','1',1); }
				if (id=='video_01' && !$('#video_01').find(".btn_wide").hasClass("on")){
					$(this).attr('title','넓은화면 끄기');
				}
				if (id=='video_01' && $('#video_01').find(".btn_wide").hasClass("on")){
					$(this).attr('title','넓은화면 켜기');
					setCookiepop('player_opt','0',1)
				}
				if (id!='video_01' && !$('#video_02').find(".btn_small").hasClass("on")){
						$('#video_02').find(".btn_wide").attr('title','넓은화면 끄기');
						$('#video_03').find(".btn_wide").attr('title','넓은화면 끄기');
				}
				if (id!='video_01' && $('#video_02').find(".btn_small").hasClass("on")){
						$('#video_02').find(".btn_wide").attr('title','넓은화면 켜기');
						$('#video_03').find(".btn_wide").attr('title','넓은화면 켜기');
				}
				if (id=='video_01'){
				  $(".player_box").removeClass("size_small");
				  $(".player_box").toggleClass("size_wide");
				  $('#video_01').find(".btn_small").removeClass("on");
				  $('#video_01').find(".btn_wide").toggleClass("on");
				  resizeVideoJS('');
				}else{
					$('#video_01').find(".btn_small ").click();
				}
				 if ($('#video_01').find(".btn_small").hasClass("on")){
					$('#video_02').find(".btn_wide").removeClass("on").addClass("on");
					$('#video_03').find(".btn_wide").removeClass("on").addClass("on");
				 }
				 if ($('#video_01').find(".btn_wide").hasClass("on")){
					$('#video_02').find(".btn_wide").removeClass("on");
					$('#video_03').find(".btn_wide").removeClass("on");
				 }
				 if (!$('#video_01').find(".btn_wide").hasClass("on") && !$('#video_01').find(".btn_small").hasClass("on")){
					$('#video_02').find(".btn_wide").removeClass("on");
					$('#video_03').find(".btn_wide").removeClass("on");
				 }
				 
			});

			// 설치형 플레이어 클릭
			$('#'+id).find(".btn_download").click(function() {
				if (rtsp_start==1){
					$(".player_install .btn_download").addClass("on");
					win.confirm('안내', '현재 설치형 플레이어로 시청 중입니다.</br>일반 플레이로 전환하시겠습니까?</br>', function (r) {
							if (r==true){
								$('.btn_download').attr('title','설치형플레이어 안내 열기');
								$(".player_install .btn_download").removeClass("on");
								dp_chg_flag=1;
								var vod_type='';
								var play_url='';
								var timestamp = new Date().getTime();

								if (vsrc!=''){ play_url=vsrc+'?'+timestamp; }
								if (play_url.indexOf('.m3u8')>0){ vod_type='application/x-mpegURL'; }
								videojs('YoonVideo_'+player_id_[1]).src([ { type: vod_type, src: '' } ]);	
								var el =  videojs('YoonVideo_'+player_id_[1]).tech({ IWillNotUseThisInPlugins: true }).el();
								el.src = '';
								rtsp_start=0
								rtsp_stop(0);
								setTimeout(function(){ 
									$('#app').find('img').attr('src','./images/test_btn_app.png');
									videojs('YoonVideo_'+player_id_[1]).src([ { type: vod_type, src: play_url } ]);	
									if ( navigator.userAgent.match(/Trident.*rv\:11\./) ){
										videojs('YoonVideo_'+player_id_[1]).load();
										setTimeout(function(){ videojs('YoonVideo_'+player_id_[1]).play(); },100);
									}else{
										videojs('YoonVideo_'+player_id_[1]).play();
									}
									err_flags=0;rtsp_wait=0;

									
									
								},100);
								$('#'+id).find('.vjs-poster').hide();
								
							}else{
								 $(".player_install .btn_download").addClass("on");
							}
					});
					return;
				}
				var tip_xy = $(this).offset();
				$('#rtsp_tip_msg').css("top",parseInt(tip_xy.top, 10)+12);
				$('#rtsp_tip_msg').css("left",tip_xy.left);
				if ($('#rtsp_tip_msg').css("display") != "none"){
					$('#rtsp_tip_msg').hide();
				}else{
					$('#rtsp_tip_msg').show();
				}
				
			});
			//resizeVideoJS();
		}
		
		function resizeVideoJS(player_id){
					
					var aspectRatio = 720/1280; 
					var width_body = document.body.offsetWidth;

					$(".videobox").each(function() {
						var rel_id=$(this).attr('id');
						var player_id_ = rel_id.split('_');

						var width_video = $(this).attr('style');
						var height = 0;
						var width = 0;
						

						if (player_id_[1]=='01'){
							width = document.getElementById('mediaBox_'+player_id_[1]).parentElement.offsetWidth;
							/*height =  width * aspectRatio+33;*/
							height =  width * aspectRatio;
						}
						if (player_id_[1]=='02' || player_id_[1]=='03' ){
							width = document.getElementById('video_'+player_id_[1]).offsetWidth;
							/*height =  width * aspectRatio+26;*/
							height =  width * aspectRatio;
							//alert(width); // video_box
						}
						var size = parseInt(width, 10);

						console.log('==> mediaBox_'+player_id_[1]+'----'+width);
					
						if (player_id_[1]=='01' ){
								/*height=height-1;*/
								$("#mediaBox_"+player_id_[1]).attr('style', 'height: '+height+'px !important');
						}

						if (player_id_[1]=='02' || player_id_[1]=='03' ){
								$("#mediaBox_"+player_id_[1]).attr('style', 'height: '+height+'px !important');
								//$("#video_"+player_id_[1]).attr('style', 'height: '+height+'px !important');
						}
					});
					
		}
		//alert(1);		
		window.onresize = resizeVideoJS; 


		//replaceAll prototype 선언
		String.prototype.replaceAll_ = function(org, dest) {
			return this.split(org).join(dest);
		}

		function numFormat(variable) { variable = Number(variable).toString(); if(Number(variable) < 10 && variable.length == 1) variable = "0" + variable; return variable; }
	
		function rpad(str, padLen, padStr) {
				if (padStr.length > padLen) {
					return str + "";
				}
				str += ""; // 문자로
				padStr += ""; // 문자로
				while (str.length < padLen)
					str += padStr;
				str = str.length >= padLen ? str.substring(0, padLen) : str;
				return str;
		}

		function log_(a){
				return;
				let today = new Date();   
				let hours = today.getHours(); // 시
				let minutes = today.getMinutes();  // 분
				let seconds = today.getSeconds();  // 초
				let milliseconds = today.getMilliseconds(); // 밀리초
				let stamp=numFormat(hours) + ':' + numFormat(minutes) + ':' + numFormat(seconds) + '.' + milliseconds;
				$('#info').val($('#info').val()+"[VideoJs Event] "+rpad(a,10," ")+" ("+stamp+")\r\n");	
		}

		var TimeFormat_str = function(totalsecond) {
				var second = Math.floor(totalsecond % 60);
				var minute = Math.floor(Math.floor(totalsecond / 60) % 60) ;
				var hour = Math.floor(totalsecond / 3600);
				if (second<0){second=0;}
				if (minute<0){minute=0;}
				if (hour<0){hour=0;}

				return hour+":"+((minute < 10)?"0":"")+minute+":" + ((second < 10)?"0":"")+second;
		}

		var getCookie_str = function(check_value) {
				check_value = check_value + "=";
				var x = 0;
				while (x <= document.cookie.length) {
					var y = (x + check_value.length);
					if (document.cookie.substring(x, y) == check_value) {
						if ((endOfCookie = document.cookie.indexOf(";", y)) == -1) {
							endOfCookie = document.cookie.length;
						}
						return unescape(document.cookie.substring(y, endOfCookie));
					}
					x = document.cookie.indexOf(" ", x) + 1;
					if (x == 0) {	break; }
				}
				return "";
		}

		var setCookie_str = function(check_value, set_value, day_value) {
				var todayDate = new Date();
				todayDate.setDate(todayDate.getDate() + day_value);
				document.cookie = check_value + "=" + escape(set_value) + "; path=/; expires=" + todayDate.toGMTString() + ";"
		}

		var setMediaBookMarkStyle = function(objMediaBox, objMediaPlayer, strBookmarkName, objThis, intThisIndex, intBookmarkValue) {
				$.data(objThis,"BookmarkValue",intBookmarkValue);
				$(objThis).html(TimeFormat_str(intBookmarkValue));
				objMediaBox.find(".aBookMarkReSet_" + intThisIndex).remove();
				$(objThis).parent().append(" <a href=\"javascript:void(0)\" class=\"aBookMarkReSet_" + intThisIndex + "\">[수정]</a>");
				objMediaBox.find(".aBookMarkReSet_" + intThisIndex).click(function() {
					intBookmarkValue = player.currentTime();  
					setCookie_str(strBookmarkName + intThisIndex, intBookmarkValue, 365);
					setMediaBookMarkStyle(objMediaBox, objMediaPlayer, strBookmarkName, objThis, intThisIndex, intBookmarkValue);
				});
				$(objThis).unbind("click");
				$(objThis).click(function() {
					exeMediaMoveBookMark(objMediaBox, objMediaPlayer, objThis);
				});
		}

		var exeMediaMoveBookMark = function(objMediaBox, objMediaPlayer, objThis) {
				var intBookmarkValue = parseInt($.data(objThis,"BookmarkValue"));
				player.currentTime(intBookmarkValue);
		}

