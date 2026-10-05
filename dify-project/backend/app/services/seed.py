"""Small, idempotent development data set for exercising core relationships."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Character, Clue, Script

DEVELOPMENT_SCRIPT_TITLE = "开发样例：雾港档案"


def seed_development_data(db: Session) -> Script:
    """Create the fixed development script once and return it on later runs."""
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
    db.commit()
    db.refresh(script)
    return script
