export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="mb-6 text-2xl font-bold">鲜标智投 — 隐私政策</h1>
      <div className="prose prose-sm prose-slate">
        <p className="text-slate-500">最后更新：2026 年 3 月</p>

        <h2>一、信息收集</h2>
        <p>我们收集以下信息以提供服务：</p>
        <ul>
          <li><strong>账号信息</strong>：用户名、联系方式（用于登录和通知）</li>
          <li><strong>企业信息</strong>：企业名称、资质证书、联系方式（用于生成投标文件）</li>
          <li><strong>招标文件</strong>：用户上传的 PDF/DOCX 文件（用于 AI 解析）</li>
          <li><strong>操作日志</strong>：登录时间、功能使用记录（用于安全审计）</li>
        </ul>

        <h2>二、信息使用</h2>
        <p>收集的信息仅用于：</p>
        <ul>
          <li>提供投标文件生成、合规检查等核心服务</li>
          <li>改进 AI 模型和服务质量</li>
          <li>安全审计和异常检测</li>
          <li>用户配额和计费管理</li>
        </ul>

        <h2>三、数据安全</h2>
        <ul>
          <li>所有数据采用<strong>多租户隔离</strong>机制，不同企业数据严格隔离</li>
          <li>敏感信息（密码、API Key）加密存储</li>
          <li>数据传输采用 HTTPS 加密</li>
          <li>定期进行安全审计和漏洞扫描</li>
        </ul>

        <h2>四、AI 数据处理</h2>
        <p>用户上传的招标文件和生成的投标内容将通过 AI 大模型进行处理。我们承诺：</p>
        <ul>
          <li>用户数据不会用于训练通用 AI 模型</li>
          <li>AI 处理过程中的数据不会泄露给第三方</li>
          <li>用户可以随时删除已上传的文件和生成的内容</li>
        </ul>

        <h2>五、数据保留与删除</h2>
        <p>用户注销账号后，我们将在 30 天内删除所有用户数据。法律法规要求保留的除外。</p>

        <h2>六、联系方式</h2>
        <p>如有隐私相关问题，请联系：privacy@freshbid.com</p>
      </div>
    </div>
  );
}
