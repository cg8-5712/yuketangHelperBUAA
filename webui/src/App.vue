<template>
  <div id="app" v-cloak>
    <header class="topbar">
      <div><span class="logo">YT</span><strong>雨课堂助手</strong><span class="muted">/ 多账号工作台</span></div>
      <span class="badge">本地运行 · 127.0.0.1</span>
    </header>
    <main>
      <section class="intro">
        <div><p class="eyebrow">WORKSPACE</p><h1>多个账号，一起看进度</h1><p>每个账号单独登录、单独运行。先添加 Cookie，再选择课程启动。</p></div>
        <div class="stat"><strong>{{ activeCount }}</strong><span>运行中账号</span></div>
      </section>

      <div v-if="notice" class="notice" :class="noticeType">{{ notice }}</div>

      <div v-if="qrLogin.open" class="modal-backdrop">
        <section class="modal panel">
          <div class="panel-head"><div><p class="eyebrow">QR LOGIN</p><h2>扫码添加账号</h2></div><button class="link" @click="cancelQRLogin">关闭</button></div>
          <div v-if="!qrLogin.id" class="form">
            <label>账号备注<input v-model.trim="qrLogin.label" placeholder="例如：我的账号" maxlength="80"></label>
            <label>学校域名<input v-model.trim="qrLogin.domain" placeholder="buu.yuketang.cn" required></label>
            <button class="primary" @click="startQRLogin" :disabled="busy">获取二维码</button>
          </div>
          <div v-else class="qr-login-content">
            <p class="hint">{{ qrLogin.status }}<span v-if="qrLogin.domain"> · {{ qrLogin.domain }}</span></p>
            <img v-if="qrLogin.qr_image" class="qr-image" :src="qrLogin.qr_image" alt="雨课堂登录二维码">
            <div v-else class="qr-placeholder">正在连接登录服务...</div>
            <p v-if="qrLogin.error" class="error">{{ qrLogin.error }}</p>
            <div class="modal-actions"><button class="secondary" @click="cancelQRLogin">取消</button><button v-if="qrLogin.status === '完成'" class="primary" @click="finishQRLogin">完成</button></div>
          </div>
        </section>
      </div>

      <section class="grid">
        <div class="panel">
          <div class="panel-head"><div><p class="eyebrow">01 / ACCOUNTS</p><h2>账号管理</h2></div><div class="panel-actions"><span>{{ accounts.length }} 个账号</span><button class="secondary compact" @click="openQRLogin">扫码添加</button></div></div>
          <form class="form" @submit.prevent="addAccount">
            <label>账号备注<input v-model.trim="newAccount.label" placeholder="例如：我的账号" required maxlength="80"></label>
            <label>学校域名<input v-model.trim="newAccount.domain" placeholder="buu.yuketang.cn" required></label>
            <label>Cookie<textarea v-model.trim="newAccount.cookie" rows="3" placeholder="粘贴 csrftoken 和 sessionid" required></textarea></label>
            <button class="primary" :disabled="busy">添加账号</button>
            <small>Cookie 只保存在本机 .accounts 目录，页面不会回显。</small>
          </form>
          <div class="account-list">
            <article class="account" v-for="account in accounts" :key="account.id">
              <div class="account-top"><label><input type="checkbox" v-model="selected" :value="account.id"><strong>{{ account.label }}</strong></label><button class="link danger" @click="removeAccount(account.id)">删除</button></div>
              <p>{{ account.domain }}</p>
              <div class="chips"><span :title="account.user_agent">UA 已分配</span><span>{{ account.proxy }}</span></div>
              <button class="link" @click="loadCourses(account.id)">查看课程</button> <button class="link" @click="editing = editing === account.id ? '' : account.id">更新 Cookie</button>
              <div v-if="editing === account.id" class="cookie-edit"><textarea v-model.trim="replacementCookie" rows="3" placeholder="粘贴新的 csrftoken 和 sessionid"></textarea><button class="secondary" @click="updateCookie(account.id)">保存 Cookie</button></div>
              <div v-if="courseLists[account.id]" class="course-list"><span v-for="course in courseLists[account.id]" :key="course.id">{{ course.name }}</span></div>
            </article>
            <p v-if="!accounts.length" class="empty">还没有账号。添加后就能选择并启动。</p>
          </div>
        </div>

        <div class="stack">
          <section class="panel">
            <div class="panel-head"><div><p class="eyebrow">02 / RUN</p><h2>启动任务</h2></div><span>最多 8 个账号</span></div>
            <p class="hint">选中左侧账号后启动。同一账号不会重复运行；每个账号内部使用 4 个视频 worker。</p>
            <label>课程范围<select v-model="courseId"><option value="">全部课程</option><option v-for="course in commonCourses" :key="course.id" :value="course.id">{{ course.name }}</option></select></label>
            <p class="hint">单门课程选项来自所选账号共有的课程；先点“查看课程”加载。</p>
            <label class="inline"><input type="checkbox" v-model="doHomework"> 视频后完成选择题和填空题</label>
            <label v-if="doHomework">AI 接口<select v-model="apiMode"><option value="chat_completions">Chat Completions</option><option value="responses">Responses</option></select></label>
            <p v-if="doHomework" class="hint">需要根目录 config.json；讨论题需人工确认，网页任务会跳过。</p>
            <button class="primary wide" @click="startTasks" :disabled="busy || !selected.length">启动 {{ selected.length }} 个账号</button>
          </section>
          <section class="panel">
            <div class="panel-head"><div><p class="eyebrow">03 / NETWORK</p><h2>UA 与代理池</h2></div><span>按账号固定分配</span></div>
            <label>User-Agent 池<textarea v-model="uaText" rows="5" placeholder="每行一个 UA"></textarea></label>
            <label>代理池<textarea v-model="proxyText" rows="4" placeholder="每行一个 http://host:port；留空使用本机网络"></textarea></label>
            <button class="secondary" @click="savePools" :disabled="busy">保存池设置</button>
            <p class="hint">代理地址决定实际出口 IP；修改 UA 不会改变 IP。池设置只影响新启动的任务。</p>
          </section>
        </div>
      </section>

      <section class="panel tasks">
        <div class="panel-head"><div><p class="eyebrow">04 / LIVE</p><h2>实时任务</h2></div><span>每 2 秒刷新</span></div>
        <div v-if="!tasks.length" class="empty">任务会显示在这里。</div>
        <article v-for="task in tasks" :key="task.id" class="task">
          <div class="task-head"><div><strong>{{ task.label }}</strong><span class="muted">{{ task.course || '准备课程...' }}</span></div><div><span class="status" :class="statusClass(task.status)">{{ task.status }}</span><button v-if="active(task)" class="link danger" @click="stopTask(task.id)">停止</button></div></div>
          <p v-if="task.error" class="error">{{ task.error }}</p>
          <div class="workers"><div v-for="worker in ['Worker1','Worker2','Worker3','Worker4']" :key="worker" class="worker"><span>{{ worker }}</span><span class="video-name">{{ task.workers[worker]?.video || '待命' }}</span><div class="track"><div class="fill" :style="{width: Math.round((task.workers[worker]?.progress || 0) * 100) + '%'}"></div></div><span class="worker-detail">{{ task.workers[worker]?.status || '待命' }} {{ task.workers[worker]?.detail || '' }}</span></div></div>
        </article>
      </section>
    </main>
  </div>
</template>

<script>
export default {
  data() { return {
    accounts: [], tasks: [], selected: [], courseLists: {}, courseId: '',
    newAccount: {label: '', domain: '', cookie: ''}, uaText: '', proxyText: '',
    doHomework: false, apiMode: 'chat_completions', editing: '', replacementCookie: '',
    notice: '', noticeType: '', busy: false, timer: null,
    qrLogin: {open: false, id: '', label: '', domain: '', status: '', qr_image: '', error: '', timer: null},
  }},
  computed: {
    activeCount() { return this.tasks.filter(this.active).length },
    commonCourses() {
      const lists = this.selected.map(id => this.courseLists[id]).filter(Boolean)
      if (lists.length !== this.selected.length || !lists.length) return []
      return lists[0].filter(course => lists.every(list => list.some(item => item.id === course.id)))
    },
  },
  methods: {
    async api(path, options = {}) {
      const response = await fetch(path, {headers: {'Content-Type': 'application/json'}, ...options})
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`)
      return data
    },
    flash(message, error = false) { this.notice = message; this.noticeType = error ? 'error' : '' },
    async load() {
      try {
        const [accounts, tasks, pools] = await Promise.all([this.api('/api/accounts'), this.api('/api/tasks'), this.api('/api/pools')])
        this.accounts = accounts; this.tasks = tasks
        this.uaText = pools.user_agents.join('\n'); this.proxyText = pools.proxies.join('\n')
      } catch (error) { this.flash(error.message, true) }
    },
    async refresh() { try { this.tasks = await this.api('/api/tasks') } catch (error) { this.flash(error.message, true) } },
    async act(fn, success) {
      this.busy = true
      try { await fn(); this.flash(success) } catch (error) { this.flash(error.message, true) } finally { this.busy = false }
    },
    async addAccount() { await this.act(async () => { await this.api('/api/accounts', {method: 'POST', body: JSON.stringify(this.newAccount)}); this.newAccount = {label: '', domain: '', cookie: ''}; this.accounts = await this.api('/api/accounts') }, '账号已添加') },
    async removeAccount(id) {
      if (!confirm('确定删除这个账号和本地 Cookie 吗？')) return
      await this.act(async () => { await this.api(`/api/accounts/${id}`, {method: 'DELETE'}); this.accounts = await this.api('/api/accounts'); this.selected = this.selected.filter(item => item !== id) }, '账号已删除')
    },
    async loadCourses(id) { await this.act(async () => { const data = await this.api(`/api/accounts/${id}/courses`); this.courseLists[id] = data.courses }, '课程列表已加载') },
    async updateCookie(id) { await this.act(async () => { await this.api(`/api/accounts/${id}/cookie`, {method: 'PUT', body: JSON.stringify({cookie: this.replacementCookie})}); this.replacementCookie = ''; this.editing = '' }, 'Cookie 已更新') },
    openQRLogin() { this.qrLogin.open = true },
    async startQRLogin() {
      this.busy = true
      try {
        const data = await this.api('/api/login/qr', {method: 'POST', body: JSON.stringify({label: this.qrLogin.label, domain: this.qrLogin.domain})})
        Object.assign(this.qrLogin, data)
        this.qrLogin.open = true
        this.qrLogin.timer = setInterval(() => this.pollQRLogin(), 1000)
        await this.pollQRLogin()
      } catch (error) { this.flash(error.message, true) } finally { this.busy = false }
    },
    async pollQRLogin() {
      if (!this.qrLogin.id) return
      try {
        const data = await this.api(`/api/login/qr/${this.qrLogin.id}`)
        Object.assign(this.qrLogin, data)
        if (['完成', '失败', '已取消'].includes(data.status)) {
          clearInterval(this.qrLogin.timer); this.qrLogin.timer = null
          if (data.status === '完成') { this.accounts = await this.api('/api/accounts'); this.flash('扫码登录成功，账号已添加') }
        }
      } catch (error) { this.flash(error.message, true) }
    },
    async cancelQRLogin() {
      if (this.qrLogin.id && !['完成', '失败', '已取消'].includes(this.qrLogin.status)) {
        try { await this.api(`/api/login/qr/${this.qrLogin.id}/cancel`, {method: 'POST', body: '{}'}) } catch (error) { this.flash(error.message, true) }
      }
      clearInterval(this.qrLogin.timer); this.qrLogin.timer = null
      this.qrLogin = {open: false, id: '', label: '', domain: '', status: '', qr_image: '', error: '', timer: null}
    },
    finishQRLogin() { this.cancelQRLogin() },
    async savePools() {
      await this.act(async () => { await this.api('/api/pools', {method: 'PUT', body: JSON.stringify({user_agents: this.uaText.split('\n').map(s => s.trim()).filter(Boolean), proxies: this.proxyText.split('\n').map(s => s.trim()).filter(Boolean)})}); this.accounts = await this.api('/api/accounts') }, '池设置已保存，新任务将使用更新后的配置')
    },
    async startTasks() { await this.act(async () => { await this.api('/api/tasks', {method: 'POST', body: JSON.stringify({account_ids: this.selected, course_name: this.courseId || null, do_homework: this.doHomework, api_mode: this.apiMode})}); await this.refresh() }, '任务已启动') },
    async stopTask(id) { await this.act(async () => { await this.api(`/api/tasks/${id}/stop`, {method: 'POST', body: '{}'}); await this.refresh() }, '已发送停止信号') },
    active(task) { return ['启动中', '运行中', '停止中'].includes(task.status) },
    statusClass(status) { return status === '运行中' ? 'running' : status === '失败' ? 'failed' : '' },
  },
  mounted() { this.load(); this.timer = setInterval(() => this.refresh(), 2000) },
  beforeUnmount() { clearInterval(this.timer); clearInterval(this.qrLogin.timer) },
}
</script>
