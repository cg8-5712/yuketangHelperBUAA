const { createApp } = Vue;

createApp({
  data() { return {
    accounts: [], tasks: [], selected: [], courseLists: {}, courseId: '',
    newAccount: {label:'', domain:'', cookie:''}, uaText:'', proxyText:'',
    doHomework:false, apiMode:'chat_completions',
    editing:'', replacementCookie:'',
    notice:'', noticeType:'', busy:false, timer:null,
    qrLogin:{open:false,id:'',label:'',domain:'',status:'',qr_image:'',error:'',timer:null},
  }},
  computed: {
    activeCount() { return this.tasks.filter(this.active).length; },
    commonCourses() {
      const lists = this.selected.map(id => this.courseLists[id]).filter(Boolean);
      if (lists.length !== this.selected.length || !lists.length) return [];
      return lists[0].filter(course => lists.every(list => list.some(item => item.id === course.id)));
    },
  },
  methods: {
    async api(path, options={}) {
      const response = await fetch(path, {headers:{'Content-Type':'application/json'}, ...options});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      return data;
    },
    flash(message, error=false) { this.notice=message; this.noticeType=error?'error':''; },
    async load() {
      try {
        const [accounts,tasks,pools] = await Promise.all([
          this.api('/api/accounts'), this.api('/api/tasks'), this.api('/api/pools')]);
        this.accounts=accounts; this.tasks=tasks;
        this.uaText=pools.user_agents.join('\n'); this.proxyText=pools.proxies.join('\n');
      } catch(error) { this.flash(error.message,true); }
    },
    async refresh() { try {this.tasks=await this.api('/api/tasks');} catch(error) {this.flash(error.message,true);} },
    async act(fn, success) {
      this.busy=true;
      try { await fn(); this.flash(success); }
      catch(error) { this.flash(error.message,true); }
      finally { this.busy=false; }
    },
    async addAccount() {
      await this.act(async()=>{
        await this.api('/api/accounts',{method:'POST',body:JSON.stringify(this.newAccount)});
        this.newAccount={label:'',domain:'',cookie:''}; this.accounts=await this.api('/api/accounts');
      },'账号已添加');
    },
    async removeAccount(id) {
      if(!confirm('确定删除这个账号和本地 Cookie 吗？')) return;
      await this.act(async()=>{
        await this.api(`/api/accounts/${id}`,{method:'DELETE'});
        this.accounts=await this.api('/api/accounts'); this.selected=this.selected.filter(item=>item!==id);
      },'账号已删除');
    },
    async loadCourses(id) {
      await this.act(async()=>{const data=await this.api(`/api/accounts/${id}/courses`);this.courseLists[id]=data.courses;},'课程列表已加载');
    },
    async updateCookie(id) {
      await this.act(async()=>{
        await this.api(`/api/accounts/${id}/cookie`,{method:'PUT',body:JSON.stringify({cookie:this.replacementCookie})});
        this.replacementCookie=''; this.editing='';
      },'Cookie 已更新');
    },
    openQRLogin() { this.qrLogin.open=true; },
    async startQRLogin() {
      this.busy=true;
      try {
        const data=await this.api('/api/login/qr',{method:'POST',body:JSON.stringify({label:this.qrLogin.label,domain:this.qrLogin.domain})});
        Object.assign(this.qrLogin,data); this.qrLogin.open=true;
        this.qrLogin.timer=setInterval(()=>this.pollQRLogin(),1000); await this.pollQRLogin();
      } catch(error) { this.flash(error.message,true); } finally { this.busy=false; }
    },
    async pollQRLogin() {
      if(!this.qrLogin.id) return;
      try {
        const data=await this.api(`/api/login/qr/${this.qrLogin.id}`); Object.assign(this.qrLogin,data);
        if(['完成','失败','已取消'].includes(data.status)) {
          clearInterval(this.qrLogin.timer); this.qrLogin.timer=null;
          if(data.status==='完成') { this.accounts=await this.api('/api/accounts'); this.flash('扫码登录成功，账号已添加'); }
        }
      } catch(error) { this.flash(error.message,true); }
    },
    async cancelQRLogin() {
      if(this.qrLogin.id&&!['完成','失败','已取消'].includes(this.qrLogin.status)) {
        try { await this.api(`/api/login/qr/${this.qrLogin.id}/cancel`,{method:'POST',body:'{}'}); } catch(error) { this.flash(error.message,true); }
      }
      clearInterval(this.qrLogin.timer); this.qrLogin.timer=null;
      this.qrLogin={open:false,id:'',label:'',domain:'',status:'',qr_image:'',error:'',timer:null};
    },
    finishQRLogin() { this.cancelQRLogin(); },
    async savePools() {
      await this.act(async()=>{
        await this.api('/api/pools',{method:'PUT',body:JSON.stringify({
          user_agents:this.uaText.split('\n').map(s=>s.trim()).filter(Boolean),
          proxies:this.proxyText.split('\n').map(s=>s.trim()).filter(Boolean),
        })}); this.accounts=await this.api('/api/accounts');
      },'池设置已保存，新任务将使用更新后的配置');
    },
    async startTasks() {
      await this.act(async()=>{
        await this.api('/api/tasks',{method:'POST',body:JSON.stringify({
          account_ids:this.selected,course_name:this.courseId || null,
          do_homework:this.doHomework,api_mode:this.apiMode,
        })}); await this.refresh();
      },'任务已启动');
    },
    async stopTask(id) {
      await this.act(async()=>{await this.api(`/api/tasks/${id}/stop`,{method:'POST',body:'{}'});await this.refresh();},'已发送停止信号');
    },
    active(task) { return ['启动中','运行中','停止中'].includes(task.status); },
    statusClass(status) { return status==='运行中'?'running':status==='失败'?'failed':''; },
  },
  mounted() { this.load(); this.timer=setInterval(()=>this.refresh(),2000); },
  beforeUnmount() { clearInterval(this.timer); clearInterval(this.qrLogin.timer); },
}).mount('#app');
