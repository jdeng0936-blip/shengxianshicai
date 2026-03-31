export default function DisclaimerPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="mb-6 text-2xl font-bold">鲜标智投 — AI 生成内容免责声明</h1>
      <div className="prose prose-sm prose-slate">
        <p className="text-slate-500">最后更新：2026 年 3 月</p>

        <div className="rounded-lg border-2 border-amber-200 bg-amber-50 p-4">
          <p className="font-bold text-amber-800">重要提示</p>
          <p className="text-amber-700">
            本平台生成的所有投标文件内容均由人工智能（AI）辅助生成，
            <strong>仅供参考</strong>，不构成任何法律建议、商业承诺或投标担保。
          </p>
        </div>

        <h2>一、AI 生成内容的局限性</h2>
        <ul>
          <li>AI 生成的内容可能包含不准确、不完整或不适用于特定招标项目的信息</li>
          <li>AI 无法替代专业的投标顾问或法律顾问的判断</li>
          <li>生成的数据、数值和承诺需要用户根据企业实际情况核实和调整</li>
          <li>AI 引用的法规条款可能不是最新版本</li>
        </ul>

        <h2>二、用户责任</h2>
        <p>用户在使用本平台生成投标文件时，应当：</p>
        <ul>
          <li>仔细审查所有 AI 生成的内容，确保其准确性和真实性</li>
          <li>核实所有数据、资质信息和承诺是否与企业实际情况一致</li>
          <li>确保最终提交的投标文件符合招标文件的全部要求</li>
          <li>对最终提交的投标文件内容承担全部法律责任</li>
        </ul>

        <h2>三、免责范围</h2>
        <p>本平台不对以下情况承担责任：</p>
        <ul>
          <li>因 AI 生成内容的不准确导致的投标失败</li>
          <li>因用户未核实生成内容导致的合规问题</li>
          <li>因用户提供不真实的企业信息导致的任何后果</li>
          <li>因网络中断、系统故障等不可抗力导致的服务中断</li>
        </ul>

        <h2>四、合规检查说明</h2>
        <p>
          本平台提供的合规检查和风险报告功能基于关键词匹配和 AI 语义分析，
          <strong>不能替代专业的法律审查</strong>。
          建议用户在正式投标前聘请专业人员进行最终审核。
        </p>

        <h2>五、报价免责</h2>
        <p>
          本平台提供的报价参考价格来源于公开市场数据，
          实际采购价格受地域、季节、市场供需等多种因素影响。
          <strong>最终报价由用户自行决定，平台不对报价结果承担任何责任。</strong>
        </p>
      </div>
    </div>
  );
}
