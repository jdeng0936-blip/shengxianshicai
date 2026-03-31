"""
生鲜食品法规知识库种子数据 — 预填核心法规条款到 std_document + std_clause

使用方法:
  cd backend && python -m scripts.seed_fresh_food_knowledge

注意:
  - 本脚本仅插入文本数据，向量嵌入需要另行调用 EmbeddingService 生成
  - 运行前确保数据库已迁移（std_document / std_clause 表存在）
  - tenant_id=0 表示公共数据，所有租户可用
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, text
from app.core.database import async_engine, get_async_session

# ---------- 种子数据 ----------

DOCUMENTS = [
    # ===== 食品安全法律法规 =====
    {
        "title": "中华人民共和国食品安全法（2021修订）",
        "doc_type": "food_safety_law",
        "version": "2021",
        "clauses": [
            {"clause_no": "第三十三条", "title": "食品生产经营卫生要求",
             "content": "食品生产经营应当符合食品安全标准，并符合下列要求：（一）具有与生产经营的食品品种、数量相适应的食品原料处理和食品加工、包装、贮存等场所，保持该场所环境整洁；（二）具有与生产经营的食品品种、数量相适应的生产经营设备或者设施，有相应的消毒、更衣、盥洗、采光、照明、通风、防腐、防尘、防蝇、防鼠、防虫、洗涤以及处理废水、存放垃圾和废弃物的设备或者设施。"},
            {"clause_no": "第三十四条", "title": "禁止生产经营的食品",
             "content": "禁止生产经营下列食品、食品添加剂、食品相关产品：（一）用非食品原料生产的食品或者添加食品添加剂以外的化学物质和其他可能危害人体健康物质的食品；（二）致病性微生物，农药残留、兽药残留、生物毒素、重金属等污染物质以及其他危害人体健康的物质含量超过食品安全标准限量的食品。"},
            {"clause_no": "第五十三条", "title": "食品经营者进货查验",
             "content": "食品经营者采购食品，应当查验供货者的许可证和食品出厂检验合格证或者其他合格证明。食品经营企业应当建立食品进货查验记录制度，如实记录食品的名称、规格、数量、生产日期或者生产批号、保质期、进货日期以及供货者名称、地址、联系方式等内容，并保存相关凭证。记录和凭证保存期限不得少于产品保质期满后六个月。"},
            {"clause_no": "第五十四条", "title": "食品贮存运输要求",
             "content": "食品经营者应当按照保证食品安全的要求贮存食品，定期检查库存食品，及时清理变质或者超过保质期的食品。食品经营者贮存散装食品，应当在贮存位置标明食品的名称、生产日期或者生产批号、保质期、生产者名称及联系方式等。"},
            {"clause_no": "第六十八条", "title": "食品召回制度",
             "content": "食品经营者发现其经营的食品不符合食品安全标准或者有证据证明可能危害人体健康的，应当立即停止经营，通知相关生产经营者和消费者，并记录停止经营和通知情况。"},
            {"clause_no": "第一百三十六条", "title": "免责条款",
             "content": "食品经营者履行了本法规定的进货查验等义务，有充分证据证明其不知道所采购的食品不符合食品安全标准，并能如实说明其进货来源的，可以免予处罚，但应当依法没收其不符合食品安全标准的食品。"},
        ],
    },
    # ===== 冷链物流标准 =====
    {
        "title": "GB/T 28843-2012 食品冷链物流追溯管理要求",
        "doc_type": "cold_chain_standard",
        "version": "2012",
        "clauses": [
            {"clause_no": "4.1", "title": "追溯体系基本要求",
             "content": "食品冷链物流追溯体系应覆盖从原料采购、加工、贮存、运输、配送到销售的全过程。各环节应建立完整的温度记录，确保冷链不断链。追溯信息应至少保存2年以上。"},
            {"clause_no": "4.3", "title": "运输环节温度控制",
             "content": "冷藏食品运输温度应控制在0℃~4℃；冷冻食品运输温度应控制在-18℃以下。运输车辆应配备温度记录仪，记录间隔不超过5分钟。每次运输应保留完整的温度记录数据。"},
            {"clause_no": "5.2", "title": "仓储温度分区管理",
             "content": "冷链仓储应按照食品贮存温度要求分区管理：冷藏区（0℃~4℃）、冷冻区（-18℃以下）、常温区（不超过25℃）。不同温区应有明确标识，禁止混存。库房应安装温湿度自动监控系统。"},
            {"clause_no": "5.4", "title": "车辆卫生管理",
             "content": "冷链运输车辆应每日清洁消毒，保持车厢内部清洁卫生。车辆应定期检修制冷设备，确保温控系统正常运行。每辆车应配备GPS定位和实时温度监控设备，数据可远程查看。"},
        ],
    },
    # ===== 食品生产通用卫生规范 =====
    {
        "title": "GB 14881-2013 食品安全国家标准 食品生产通用卫生规范",
        "doc_type": "food_safety_law",
        "version": "2013",
        "clauses": [
            {"clause_no": "5.1", "title": "原料采购要求",
             "content": "应建立原料供应商审核制度，对供应商的许可资质、质量管理体系、产品质量等进行评审。采购的食品原料应符合相应的食品安全国家标准或有关规定。"},
            {"clause_no": "6.3", "title": "食品加工人员卫生要求",
             "content": "食品加工人员应保持个人卫生，进入加工区域应穿戴清洁的工作服、工作帽，头发不应露出帽外。接触食品的人员应定期进行健康检查，取得健康证明后方可上岗。"},
            {"clause_no": "8.1", "title": "食品留样制度",
             "content": "集中用餐单位的食堂应当对每餐次加工制作的每种食品成品进行留样，每个品种留样量不少于125克，并记录留样食品名称、留样量、留样时间、留样人员等信息。留样食品应当由专柜冷藏保存48小时以上。"},
        ],
    },
    # ===== 学校食品安全管理 =====
    {
        "title": "学校食品安全与营养健康管理规定（教育部/市场监管总局/卫健委）",
        "doc_type": "procurement_regulation",
        "version": "2019",
        "clauses": [
            {"clause_no": "第二十条", "title": "学校食堂食品安全管理",
             "content": "学校食堂应当建立食品安全与营养健康状况自查制度，对食品安全与营养健康状况进行自查。学校食堂应当依法取得食品经营许可证，严格按照食品经营许可证载明的经营项目进行经营。"},
            {"clause_no": "第二十一条", "title": "陪餐制度",
             "content": "中小学、幼儿园应当建立集中用餐陪餐制度，每餐均应当有学校相关负责人与学生共同用餐，做好陪餐记录，及时发现和解决集中用餐过程中存在的问题。"},
            {"clause_no": "第二十八条", "title": "食材采购管理",
             "content": "学校食堂应当建立食品、食品添加剂和食品相关产品进货查验记录制度，如实准确记录名称、规格、数量、生产日期或者生产批号、保质期、进货日期以及供货者名称、地址、联系方式等内容。鼓励学校食堂采用信息化手段实现食品可追溯。"},
            {"clause_no": "第三十条", "title": "禁止采购的食品",
             "content": "学校食堂不得采购、贮存、使用亚硝酸盐（包括亚硝酸钠、亚硝酸钾）；不得加工制作四季豆、鲜黄花菜、野生蘑菇、发芽土豆等高风险食品；中小学、幼儿园食堂不得制售冷荤类食品、生食类食品、裱花蛋糕。"},
            {"clause_no": "第三十五条", "title": "营养健康管理",
             "content": "学校食堂应当根据卫生健康主管部门发布的学生营养膳食指南，针对不同年龄段在校学生营养健康需求，因地制宜引导学生科学营养用餐。有条件的地方，学校应当配备营养专业人员或聘请营养指导员。"},
        ],
    },
    # ===== 餐饮服务食品安全操作规范 =====
    {
        "title": "餐饮服务食品安全操作规范（2018）",
        "doc_type": "food_safety_law",
        "version": "2018",
        "clauses": [
            {"clause_no": "4.2", "title": "原料验收标准",
             "content": "餐饮服务提供者应当建立并执行食品原料验收制度。验收时应检查：外包装是否完整、是否在保质期内、冷藏冷冻食品的中心温度是否符合要求、感官性状是否正常。不符合要求的食品原料应当拒收。"},
            {"clause_no": "7.1", "title": "食品配送要求",
             "content": "配送食品应使用专用的密闭容器或车辆。冷藏食品配送温度应控制在0℃~8℃，冷冻食品配送温度应低于-12℃。配送时间不宜超过2小时（冷链条件下可适当延长）。配送车辆和容器应当每日清洁消毒。"},
            {"clause_no": "8.3", "title": "食品安全事故应急处置",
             "content": "餐饮服务提供者应当制定食品安全事故处置方案。发生食品安全事故后，应立即封存导致或者可能导致食品安全事故的食品及其原料、工具、设备，在2小时内报告所在地县级市场监督管理部门。配合相关部门调查处理，不得对食品安全事故隐瞒、谎报、缓报。"},
        ],
    },
    # ===== 冷链食品包装运输标准 =====
    {
        "title": "GB/T 24616-2019 冷藏、冷冻食品物流包装、标志、运输和储存",
        "doc_type": "cold_chain_standard",
        "version": "2019",
        "clauses": [
            {"clause_no": "5.1", "title": "包装要求",
             "content": "冷藏、冷冻食品的包装材料应符合食品安全国家标准要求。包装应能有效防护食品在物流过程中免受外界污染和机械损伤。冷冻食品包装应能承受-20℃以下的低温环境。"},
            {"clause_no": "6.2", "title": "运输温度要求",
             "content": "冷藏食品运输温度：0℃~10℃（具体按产品标准执行）。冷冻食品运输温度：-18℃以下。运输过程中食品温度波动不应超过±2℃。运输时间超过4小时的，应每隔1小时记录一次温度。"},
            {"clause_no": "7.1", "title": "储存要求",
             "content": "冷藏食品储存温度：0℃~4℃。冷冻食品储存温度：-18℃以下。储存区域应有温湿度自动监控报警系统。食品应离墙离地存放（离墙≥10cm，离地≥10cm），便于通风和清洁。应执行先进先出原则。"},
        ],
    },
    # ===== GB 31654-2021 餐饮服务通用卫生规范 =====
    {
        "title": "GB 31654-2021 食品安全国家标准 餐饮服务通用卫生规范",
        "doc_type": "food_safety_law",
        "version": "2021",
        "clauses": [
            {"clause_no": "6.1", "title": "采购验收要求",
             "content": "食品原料供应商应具有有效的食品生产经营许可证和产品合格证明。采购时应查验并留存供货凭证，凭证保存期限不少于产品保质期满后六个月，没有明确保质期的不少于二年。采购畜禽肉类应索取并留存动物检疫合格证明及肉品品质检验合格证明。"},
            {"clause_no": "6.2", "title": "食品贮存管理",
             "content": "食品应分区分架分类分离存放：食品与非食品不混放，生食与熟食分开存放，有毒有害物品远离食品存放区域。冷藏食品中心温度应保持在0℃~8℃，冷冻食品中心温度应保持在-12℃以下。冷藏、冷冻设施应定期维护保养和校验。"},
            {"clause_no": "7.3", "title": "加工制作过程控制",
             "content": "食品加工制作应做到烧熟煮透，加工后食品中心温度不低于70℃。食品再加热时中心温度应达到70℃以上。制作好的食品到食用时间应在2小时以内，超过2小时需在60℃以上或8℃以下的条件下保存。"},
            {"clause_no": "8.1", "title": "餐饮具清洗消毒",
             "content": "餐饮具使用后应及时洗净，消毒后在专用保洁设施内备用。已消毒的餐饮具应符合GB 14934的规定。宜采用蒸汽、煮沸消毒等物理消毒方法。集中用餐单位的餐饮具消毒应逐一进行，不应叠放消毒。"},
        ],
    },
    # ===== 政府采购法相关 =====
    {
        "title": "中华人民共和国政府采购法（2014修正）",
        "doc_type": "procurement_regulation",
        "version": "2014",
        "clauses": [
            {"clause_no": "第三条", "title": "政府采购原则",
             "content": "政府采购应当遵循公开透明原则、公平竞争原则、公正原则和诚实信用原则。政府采购应当有助于实现国家的经济和社会发展政策目标，包括保护环境、扶持不发达地区和少数民族地区、促进中小企业发展等。"},
            {"clause_no": "第二十二条", "title": "供应商资格条件",
             "content": "供应商参加政府采购活动应当具备下列条件：（一）具有独立承担民事责任的能力；（二）具有良好的商业信誉和健全的财务会计制度；（三）具有履行合同所必需的设备和专业技术能力；（四）有依法缴纳税收和社会保障资金的良好记录；（五）参加政府采购活动前三年内，在经营活动中没有重大违法记录；（六）法律、行政法规规定的其他条件。"},
            {"clause_no": "第二十六条", "title": "采购方式",
             "content": "政府采购采用以下方式：（一）公开招标；（二）邀请招标；（三）竞争性谈判；（四）单一来源采购；（五）询价；（六）国务院政府采购监督管理部门认定的其他采购方式。公开招标应作为政府采购的主要采购方式。"},
            {"clause_no": "第三十六条", "title": "废标情形",
             "content": "在招标采购中，出现下列情形之一的，应予废标：（一）符合专业条件的供应商或者对招标文件作实质响应的供应商不足三家的；（二）出现影响采购公正的违法、违规行为的；（三）投标人的报价均超过了采购预算，采购人不能支付的；（四）因重大变故，采购任务取消的。废标后，采购人应当将废标理由通知所有投标人。"},
        ],
    },
    # ===== 食品追溯管理 =====
    {
        "title": "GB/T 22005-2009 饲料和食品链的可追溯性 体系设计与实施的通用原则和基本要求",
        "doc_type": "food_safety_law",
        "version": "2009",
        "clauses": [
            {"clause_no": "4.1", "title": "可追溯性目标",
             "content": "组织应确定可追溯体系的目标和范围。食品链中的组织应能识别其直接供方和直接客户（一步向前，一步向后原则）。可追溯信息应包括产品标识、批次标识、产品转换记录、产品流向记录。"},
            {"clause_no": "5.2", "title": "追溯信息记录",
             "content": "组织应保存追溯信息记录，包括但不限于：接收记录（供方名称、日期、数量、批号）；加工记录（原料批号、成品批号、加工参数）；发货记录（客户名称、日期、数量、批号）。记录保存期限不应少于产品保质期后6个月。"},
            {"clause_no": "6.1", "title": "追溯演练与召回",
             "content": "组织应定期进行追溯演练（建议至少每年一次），以验证追溯体系的有效性。当产品发生安全问题需要召回时，应能在4小时内完成涉事批次的正向追溯（原料→成品→客户）和反向追溯（客户→成品→原料）。"},
        ],
    },
    # ===== 医院食堂管理 =====
    {
        "title": "医院食堂卫生管理办法",
        "doc_type": "procurement_regulation",
        "version": "2020",
        "clauses": [
            {"clause_no": "第五条", "title": "医院食堂基本要求",
             "content": "医院食堂应当取得食品经营许可证，配备食品安全管理员。食品加工场所面积应与供餐规模相适应。医院食堂应设立治疗膳食加工区域，与普通膳食分开操作。治疗膳食应涵盖糖尿病餐、肾病餐、流质餐、半流质餐、低盐餐等特殊饮食。"},
            {"clause_no": "第八条", "title": "食材配送特殊要求",
             "content": "医院食材配送应执行24小时应急配送制度。配送人员进入医院食堂区域前应进行健康检查登记。食材应按照普通膳食和治疗膳食需求分类配送。生鲜食材从采购到加工不超过24小时，冷冻食材应全程冷链运输。"},
            {"clause_no": "第十二条", "title": "营养科协作",
             "content": "医院食堂应在营养科指导下制定每周食谱。食谱应满足不同疾病患者的营养需求。膳食营养标签应标明热量、蛋白质、脂肪、碳水化合物、钠等主要营养素含量。每季度应由营养科评估膳食供应质量。"},
        ],
    },
]


async def seed():
    """插入种子数据"""
    from app.models.standard import StdDocument, StdClause

    async for session in get_async_session():
        # 检查是否已有数据
        result = await session.execute(
            select(StdDocument).limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing:
            print(f"std_document 表已有数据（首条: {existing.title}），跳过种子插入")
            print("如需重新导入，请先清空 std_document 和 std_clause 表")
            return

        total_docs = 0
        total_clauses = 0

        for doc_data in DOCUMENTS:
            doc = StdDocument(
                title=doc_data["title"],
                doc_type=doc_data["doc_type"],
                version=doc_data.get("version"),
                is_current=True,
                tenant_id=0,  # 公共数据
                created_by=0,
            )
            session.add(doc)
            await session.flush()
            total_docs += 1

            for i, clause_data in enumerate(doc_data.get("clauses", [])):
                clause = StdClause(
                    document_id=doc.id,
                    clause_no=clause_data.get("clause_no"),
                    title=clause_data.get("title"),
                    content=clause_data.get("content"),
                    level=0,
                    tenant_id=0,
                )
                session.add(clause)
                total_clauses += 1

        await session.commit()
        print(f"种子数据导入完成: {total_docs} 份文档, {total_clauses} 条条款")

        # ===== 第二步: 中标案例种子数据 =====
        print("\n导入中标案例...")
        await seed_bid_cases(session)

        # ===== 第三步: 生成向量嵌入 =====
        print("\n开始生成向量嵌入...")
        await generate_embeddings(session)


async def seed_bid_cases(session):
    """插入中标案例种子数据"""
    from app.models.standard import BidCase

    result = await session.execute(select(BidCase).limit(1))
    if result.scalar_one_or_none():
        print("bid_case 表已有数据，跳过")
        return

    cases = [
        BidCase(
            title="XX市第一中学2025年食材配送项目",
            customer_type="school",
            buyer_name="XX市第一中学",
            bid_amount="480000",
            discount_rate="8%",
            summary="中标亮点：自建冷链中心距学校3km，5辆冷藏车保障6:00前到校；"
                    "营养师持证上岗，每周制定带量食谱；农残快检100%覆盖，检测报告同步家长微信群",
            tenant_id=0, created_by=0,
        ),
        BidCase(
            title="XX市人民医院2025年食材配送项目",
            customer_type="hospital",
            buyer_name="XX市人民医院",
            bid_amount="1200000",
            discount_rate="6%",
            summary="中标亮点：24小时应急配送能力；治疗膳食覆盖8种特殊饮食(糖尿病/肾病/流质等)；"
                    "HACCP+ISO22000双认证；配送人员每日体温检测+核酸",
            tenant_id=0, created_by=0,
        ),
        BidCase(
            title="XX区政府机关食堂2025年食材配送项目",
            customer_type="government",
            buyer_name="XX区机关事务管理局",
            bid_amount="650000",
            discount_rate="10%",
            summary="中标亮点：全程可追溯系统对接政务平台；99.8%准时率；"
                    "价格透明度高(每日公示采购价与市场价对比)；零投诉记录",
            tenant_id=0, created_by=0,
        ),
        BidCase(
            title="XX科技园企业食堂2025年食材配送项目",
            customer_type="enterprise",
            buyer_name="XX科技园管委会",
            bid_amount="350000",
            discount_rate="12%",
            summary="中标亮点：菜品丰富度高(每周不重样)；VIP会议餐定制服务；"
                    "月度满意度调查≥95%；ERP系统自动对账",
            tenant_id=0, created_by=0,
        ),
    ]
    for case in cases:
        session.add(case)
    await session.commit()
    print(f"中标案例导入完成: {len(cases)} 条")


async def generate_embeddings(session):
    """为所有缺少 embedding 的 StdClause 生成向量"""
    from app.models.standard import StdClause
    from app.services.embedding_service import EmbeddingService

    emb_svc = EmbeddingService(session)

    # 查询所有没有 embedding 的条款
    result = await session.execute(
        select(StdClause).where(StdClause.embedding.is_(None))
    )
    clauses = list(result.scalars().all())

    if not clauses:
        print("所有条款已有向量嵌入，无需生成")
        return

    print(f"待生成向量: {len(clauses)} 条条款")

    # 批量生成（每批 10 条）
    batch_size = 10
    success = 0
    failed = 0

    for i in range(0, len(clauses), batch_size):
        batch = clauses[i:i + batch_size]
        texts = [
            f"{c.title or ''} {c.content or ''}"
            for c in batch
        ]

        embeddings = await emb_svc.embed_batch(texts)

        for clause, emb in zip(batch, embeddings):
            if emb is not None:
                clause.embedding = emb
                success += 1
            else:
                failed += 1

        await session.commit()
        print(f"  进度: {min(i + batch_size, len(clauses))}/{len(clauses)}")

    print(f"向量嵌入完成: {success} 成功, {failed} 失败")

    if failed > 0:
        print("提示: 部分条款向量生成失败，请检查 GEMINI_API_KEY 是否配置")


if __name__ == "__main__":
    asyncio.run(seed())
