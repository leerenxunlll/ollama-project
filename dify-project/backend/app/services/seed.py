"""Small, idempotent development data set for exercising core relationships."""

from textwrap import dedent

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Character,
    CharacterScriptChapter,
    Clue,
    Script,
    SharedScriptChapter,
)

DEVELOPMENT_SCRIPT_TITLE = "开发样例：雾港档案"


def _chapter_content(content: str) -> str:
    """Join source-wrapped lines while preserving paragraph breaks."""
    paragraphs = dedent(content).strip().split("\n\n")
    return "\n\n".join("".join(paragraph.splitlines()) for paragraph in paragraphs)


SHARED_CHAPTERS = (
    {
        "chapter_order": 1,
        "unlock_phase": "intro",
        "title": "序章：暴雨留客",
        "content": _chapter_content(
            """\
            雾港的雨从傍晚开始便没有停过。海风把水汽推过旧城区，港口的路灯在积水里晃成一片模糊的金色。旧仓库即将清点封存，几份多年前的档案仍
            没有找到合适的去处；与此同时，一桩命案让这间早该安静下来的建筑重新成为所有人的中心。

            林澈负责这里的纸本文档，许雁经营往返港区的渡船，周序常年替码头修船，叶青则在整理一篇关于港口旧事的报道。四个人都曾与这片港区发生
            过交集，也都在案发前后出现在雾港。暴雨使渡船停航，道路积水，仓库内外的人暂时无法散去。

            你们眼前只有一个已经发生的事实：有人死在旧仓库，熟悉这里的人都可能知道某些片段，却未必愿意把它们说全。警方尚未给出完整结论。接下
            来，每个人都要说明自己为何而来、何时到达，以及最希望别人不要追问的那件事。
            """
        ),
    },
    {
        "chapter_order": 2,
        "unlock_phase": "act_1",
        "title": "第一幕：被重新打开的档案",
        "content": _chapter_content(
            """\
            天色亮起后，雨势稍缓，旧仓库周围仍被临时封锁。初步询问没有立刻带来答案，反而让几段互不相连的旧经历重新摆到桌面上：有人熟悉仓库的
            文书，有人熟悉港口的出入，有人比旁人更了解建筑的维护情况，也有人一直在追问旧港留下的空白。

            调查从案发前后的来往开始。每个人都可以回忆自己亲眼见过的事，也可以选择暂时保留不愿公开的私人经历。公开谈话并不等于正式搜证；关于
            现场的具体物件与记录，仍要由调查行动逐一确认。
            """
        ),
    },
    {
        "chapter_order": 3,
        "unlock_phase": "act_2",
        "title": "第二幕：旧事回到桌面",
        "content": _chapter_content(
            """\
            讨论持续了一段时间，最初那些简短的回答已经不足以解释四个人为何都牵挂着旧仓库。港区的旧事开始影响眼前的判断：同一句话在不同人的记
            忆里有不同分量，一次迟疑也可能来自恐惧、羞愧，或只是对被误解的厌倦。

            第二幕没有替任何人宣布结论。新的谈话让每个人有机会补充自己的经历、解释此前的沉默，并重新审视其他人的说法。真正被调查确认的线索仍
            以搜证记录为准；私人回忆和推测可以帮助你理解人物，却不能代替证据。
            """
        ),
    },
)

PRIVATE_CHAPTERS = {
    "林澈": (
        {
            "chapter_order": 1,
            "unlock_phase": "intro",
            "title": "林澈：归档以前",
            "content": _chapter_content(
                """\
            你在雾港档案室工作了七年。旧仓库里的纸张怕潮，标签怕褪色，你习惯把每一份资料放回固定位置，再在登记簿上留下能够追溯的记号。多年前
            ，一位负责清点的人请你临时挪走一份档案，理由是原处漏水。你照做了，却没有及时补上完整的交接记录。那不是为了销毁内容，但每次有人问
            起，你仍会先想到自己当时的疏忽。

            案发前，你回到仓库核对一批待封存的纸本文档。你发现有一份旧记录仍未找到，正是你一直想补回的那一份。你没有把这件事告诉所有人，因为
            它听起来很像你在替自己开脱。你认为许雁做事谨慎，却不确定她为什么总在意旧档案；周序熟悉仓库的实际状况，叶青则会把没有核实的细节写
            进问题里。

            你来到现场，是为了找回缺失记录并说明自己为何在这里。先确认别人说的时间与地点，再决定是否提起那次挪档。
            """
            ),
        },
        {
            "chapter_order": 2,
            "unlock_phase": "act_1",
            "title": "林澈：没有补完的登记",
            "content": _chapter_content(
                """\
            第一轮询问开始后，你意识到自己不能只靠“我一直在整理档案”来回答问题。你记得自己在案发前回到仓库核对纸本资料，也记得那份始终没有
            找到的记录；至于具体的进出顺序，你应当只说自己确实确认过的部分，不要为了显得可靠而替空白补上猜测。

            你仍没有公开那次临时挪档的全部缘由。你担心它会让所有人把注意力放到一份失踪文件上，却也明白继续隐瞒会让任何遗漏都显得可疑。你对周
            序的沉默尤其在意，因为他平常不爱解释；对叶青则保持礼貌，但会留意她的问题是否建立在已经核实的事实之上。你的目标仍是找回记录，并把
            自己的责任限定在真实发生过的事里。
            """
            ),
        },
        {
            "chapter_order": 3,
            "unlock_phase": "act_2",
            "title": "林澈：把空白留在原处",
            "content": _chapter_content(
                """\
            谈话进入第二幕后，你开始分辨两种不同的压力：一边是想尽快找回记录的急切，一边是害怕别人把档案管理上的失误等同于更严重的行为。你不
            能让后一种恐惧替你决定事实。那次挪动确实发生过，交接没有做完整也确实是你的责任；除此之外，你不会替任何人推断档案后来去了哪里。

            你愿意把已核实的工作习惯和来往顺序说清楚，也愿意回答别人对那份记录的追问。你仍觉得许雁知道一些与旧文件有关的背景，但不打算把她的
            沉默当作证据。接下来先找出哪些问题能由现有记录回答，再决定是否补充自己的隐瞒。
            """
            ),
        },
    ),
    "许雁": (
        {
            "chapter_order": 1,
            "unlock_phase": "intro",
            "title": "许雁：没有署名的来信",
            "content": _chapter_content(
                """\
            你经营一条往返港区与旧城区的小型渡船。许多年前，港口还没有现在这样安静，你靠着熟悉潮汐和熟客的习惯维持生意。近来你收到一封没有署
            名的信，信里提到旧仓库和一份被遗忘的旧档案，却没有说明写信的人是谁，也没有给出足以判断真假的细节。你没有把信交给别人，只把它留在
            心里反复琢磨。

            案发前，你曾为港区的行程做安排，也因此有理由出现在旧仓库附近。你不愿让一封来历不明的信决定别人如何看待你，但你确实想知道寄信的人
            是谁。林澈像是一直在寻找某份资料，周序对仓库很熟，叶青会把观察写成报道；你还不能确认谁与那封信有关。

            暴雨让渡船停航，你留在港区。你来到这里，是想弄清信件与旧仓库之间的联系，同时避免把未经证实的猜测说成事实。
            """
            ),
        },
        {
            "chapter_order": 2,
            "unlock_phase": "act_1",
            "title": "许雁：航线之外",
            "content": _chapter_content(
                """\
            调查开始后，你可以说明渡船何时停航、自己为何留在港区，以及哪些行程是你亲自安排的。你熟悉海边的天气和船只的习惯，但这不意味着你能
            替旧仓库里发生的事作证。别人若把你的路线与仓库联系起来，你会要求他们先说清楚依据。

            那封信仍压在你的心事里。你尚未公开它，是因为你担心一旦提起，所有人都会把它当成一条现成答案；可若寄信人就在眼前，继续沉默也可能让
            你错过辨认对方反应的机会。你觉得林澈对档案的焦虑不像装出来的，周序则总把回答缩到最短。你想确认谁知道信里的旧事，但不会凭语气给任
            何人定罪。
            """
            ),
        },
        {
            "chapter_order": 3,
            "unlock_phase": "act_2",
            "title": "许雁：让来信接受追问",
            "content": _chapter_content(
                """\
            第二幕里，旧仓库不再只是一个地点，也成了每个人解释过去的借口。你决定不再把来信当作只能独自保存的秘密。若被问到，你可以承认自己收
            到过一封提及旧仓库的无署名信，但要明确哪些内容你记得、哪些地方你无法确认。你仍不知道写信人是谁，也不该把自己的怀疑包装成目击事实
            。

            你开始留意谁会急着替信件下结论，谁会追问它到达的时间。林澈对遗失记录的执着可能只是工作责任，也可能藏着难以启齿的失误；周序的沉默
            让你不安，却还不能说明原因。你的目标是找到寄信人，并让这件事进入可以被核对的讨论，而不是让它成为指向某人的暗示。
            """
            ),
        },
    ),
    "周序": (
        {
            "chapter_order": 1,
            "unlock_phase": "intro",
            "title": "周序：侧门没有扣上",
            "content": _chapter_content(
                """\
            你在雾港修船多年，习惯先看磨损、松动和受力，再决定一个东西还能不能撑住。旧仓库的门和墙你都熟悉，许多细节不用图纸也记得。案发当晚
            ，你知道仓库侧门没有上锁。这个事实本身已经足以引来追问，而你更清楚自己并非与命案毫无关系：你是必须守住秘密的人。你不愿让家人被卷
            进旧仓库的事，也不想让别人从你的沉默里拼出更多。

            你来到现场时，暴雨正在压低港区的声音。你可以谈工作、天气和自己熟悉的建筑状况，却会避开那些能把你与案发直接连在一起的问题。林澈会
            追问记录，许雁似乎有一件不愿公开的事，叶青的观察太敏锐。

            你想把谈话控制在眼前能够确认的范围内。不要主动提供超出自己已知内容的解释，也不要把家人的经历带进这场调查。
            """
            ),
        },
        {
            "chapter_order": 2,
            "unlock_phase": "act_1",
            "title": "周序：少说一个细节",
            "content": _chapter_content(
                """\
            第一幕开始后，别人会问起仓库结构和案发当晚的出入情况。你确实知道侧门没有上锁，不能把记忆改成相反的说法；你只能决定何时说出这一点
            ，以及是否承认自己早就注意到了。说得过于轻松会显得刻意，解释得太多又可能引来更多问题。

            林澈提到档案时，你会担心旧事把注意力引向自己；许雁的追问让你怀疑她知道一部分情况；叶青则可能把一次停顿写成结论。你希望别人先谈已
            经核实的现场，再谈各自的猜测。你的目标不是替调查者编答案，而是避免让家人和你真正隐瞒的事一起暴露。
            """
            ),
        },
        {
            "chapter_order": 3,
            "unlock_phase": "act_2",
            "title": "周序：沉默也会留下痕迹",
            "content": _chapter_content(
                """\
            谈话进入第二幕，你发现只回答眼前的问题并不能让怀疑消失。你知道侧门未上锁这件事会被反复提起，也知道自己对命案负有责任。你不打算主
            动承认全部经过，但也不能凭空编造新的事实去堵住别人。每一次否认都可能迫使你再说更多，每一次沉默也会让旁人继续推测。

            你仍把家人放在心上，因此最先想到的是如何阻止旧仓库的事牵连他们。可你也明白，这份保护欲不能替你改变已经发生的事。面对林澈关于记录
            的问题、许雁关于来信的暗示、叶青具体的追问，你需要谨慎区分自己亲历的事实和别人推出来的结论。
            """
            ),
        },
    ),
    "叶青": (
        {
            "chapter_order": 1,
            "unlock_phase": "intro",
            "title": "叶青：时间不明的照片",
            "content": _chapter_content(
                """\
            你是地方记者，最近一直在整理一篇关于雾港旧事的报道。你手里保存着一张拍摄时间不明的照片，画面不足以单独证明什么，文件信息也无法帮
            你确定它拍摄于哪一天。你不想让一张模糊的照片成为耸动标题，却始终没找到合适的人替你确认时间。

            案发前后，你因报道来到港区，也在旧仓库附近停留过。你习惯追问具体时刻、路线和说话原句，因为“差不多”往往掩盖了关键差别；但你也知
            道，问题问得尖锐不等于答案就是真的。林澈看重档案，许雁像是在等一个人的消息，周序熟悉港口建筑。你对三人的印象都还不完整。

            暴雨封住了离开的路，你决定先弄清案发前后每个人为何留在这里，再判断照片是否与报道有关。
            """
            ),
        },
        {
            "chapter_order": 2,
            "unlock_phase": "act_1",
            "title": "叶青：问题必须落到时间上",
            "content": _chapter_content(
                """\
            第一轮调查给了你重新核对记忆的机会。你可以说明自己来港区是为了报道，也可以承认自己有一张时间无法确认的照片；但照片的存在不能替你
            证明拍摄地点、人物或日期。你会把亲眼看到的内容和后来听到的说法分开，避免让采访笔记越过证据。

            林澈对档案的细节很敏感，似乎怕一个小小的时间差被误读；许雁回答平静，却没有把所有心事放到桌面上；周序讲起建筑时很具体，讲到自己何
            时到场时却格外简短。你想知道这些差异从何而来，但不会因为一个人不愿回答就断言他有罪。
            """
            ),
        },
        {
            "chapter_order": 3,
            "unlock_phase": "act_2",
            "title": "叶青：报道不是判决",
            "content": _chapter_content(
                """\
            第二幕开始后，你的报道计划显得不那么重要了。照片仍没有可靠的拍摄时间，不能被拿来替任何人的行踪背书。你可以把它作为自己为何来到雾
            港的背景，却应避免把它说成正式线索。真正需要核实的是每个人能确认的经历，以及他们对同一段时间为何有不同说法。

            你重新审视自己对周序的戒心：他的简短回答值得继续追问，但并不能单独证明什么。林澈可能隐瞒的是工作上的失误，许雁或许掌握一封来历不
            明的信；这些都只是目前的印象。你希望用准确的时间线替代猜测，也提醒自己，记者提出问题的责任不等于替调查者宣布答案。
            """
            ),
        },
    ),
}


def seed_development_data(db: Session) -> Script:
    """Create the fixed development script and add only missing sample chapters."""
    existing = db.scalar(select(Script).where(Script.title == DEVELOPMENT_SCRIPT_TITLE))
    if existing is not None:
        phase3_acts = {
            "潮湿的登记页": "act_1",
            "断裂的铜扣": "act_1",
            "未署名信封": "act_2",
        }
        changed = False
        for clue in existing.clues:
            act = phase3_acts.get(clue.name)
            if act is not None and clue.act != act:
                clue.act = act
                changed = True
        changed = _seed_story_chapters(db, existing, existing.characters) or changed
        if changed:
            db.commit()
        return existing

    script = Script(
        title=DEVELOPMENT_SCRIPT_TITLE,
        summary="用于验证剧本、角色、线索与游戏局之间的数据关系。",
        theme="旧港悬疑",
        era="当代",
        atmosphere="克制、阴郁",
        difficulty="入门",
        status="ready",
    )
    script.characters = [
        Character(
            name="林澈",
            age=34,
            identity="港口档案员",
            public_background="负责整理雾港旧仓库的纸本文档。",
            private_background="曾经调换过一份档案的存放位置。",
            personality="谨慎，重视秩序。",
            speaking_style="回答简短，常确认细节。",
            personal_goal="找回一份遗失记录。",
        ),
        Character(
            name="许雁",
            age=29,
            identity="渡船经营者",
            public_background="经营往返港区与旧城区的小型渡船。",
            private_background="案发前收到一封没有署名的信。",
            personality="冷静，善于观察。",
            speaking_style="语气平和，偶尔反问。",
            personal_goal="弄清信件是谁送来的。",
        ),
        Character(
            name="周序",
            age=41,
            identity="修船师傅",
            public_background="长期在港口维修小型船只。",
            private_background="知道仓库侧门在案发当晚没有上锁。",
            personality="沉稳，戒心较强。",
            speaking_style="用词直接，少谈自己。",
            personal_goal="避免旧仓库的事牵连家人。",
            is_killer=True,
        ),
        Character(
            name="叶青",
            age=None,
            identity="地方记者",
            public_background="正在整理一篇关于港口旧案的报道。",
            private_background="保存着一张拍摄时间不明的照片。",
            personality="好奇，行动敏捷。",
            speaking_style="提问具体，节奏较快。",
            personal_goal="确认照片的拍摄时间。",
        ),
    ]
    script.clues = [
        Clue(
            name="潮湿的登记页",
            description="一页被海水浸湿的仓库出入登记。",
            act="act_1",
            location="旧仓库办公室",
            is_core=True,
            importance=3,
        ),
        Clue(
            name="断裂的铜扣",
            description="在侧门附近发现的一枚旧式铜扣。",
            act="act_1",
            location="仓库侧门",
            is_core=False,
            importance=2,
        ),
        Clue(
            name="未署名信封",
            description="一只没有寄件人信息的空信封。",
            act="act_2",
            location="渡船候船室",
            is_core=True,
            importance=2,
        ),
    ]
    db.add(script)
    db.flush()
    _seed_story_chapters(db, script, script.characters)
    db.commit()
    db.refresh(script)
    return script


def _seed_story_chapters(
    db: Session, script: Script, characters: list[Character]
) -> bool:
    """Add absent chapters to the named sample without replacing existing text."""
    changed = False
    existing_shared_orders = set(
        db.scalars(
            select(SharedScriptChapter.chapter_order).where(
                SharedScriptChapter.script_id == script.id
            )
        ).all()
    )
    for chapter in SHARED_CHAPTERS:
        if chapter["chapter_order"] in existing_shared_orders:
            continue
        db.add(SharedScriptChapter(script_id=script.id, **chapter))
        changed = True

    characters_by_name = {character.name: character for character in characters}
    for name, chapters in PRIVATE_CHAPTERS.items():
        character = characters_by_name.get(name)
        if character is None or character.script_id != script.id:
            continue
        existing_orders = set(
            db.scalars(
                select(CharacterScriptChapter.chapter_order).where(
                    CharacterScriptChapter.character_id == character.id
                )
            ).all()
        )
        for chapter in chapters:
            if chapter["chapter_order"] in existing_orders:
                continue
            db.add(CharacterScriptChapter(character_id=character.id, **chapter))
            changed = True

    return changed
