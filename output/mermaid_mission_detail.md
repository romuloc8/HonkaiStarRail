# 任务时序详细图（按弧线分）

> - 蓝色实线箭头 `-->` = 主线章节顺序
> - 蓝色虚线箭头 `-.->` = 章节内主线关键任务
> - 橙色粗箭头 `==>` = 同行任务（注明解锁前置）
> - 绿色箭头 `-->` = 开拓续闻

---

## 空间站「黑塔」

```mermaid
flowchart TD

    classDef mainCh   fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef mainTask fill:#42A5F5,stroke:#1E88E5,color:#fff,font-size:10px
    classDef comp     fill:#FF7043,stroke:#E64A19,color:#fff,font-size:10px
    classDef cont     fill:#66BB6A,stroke:#43A047,color:#fff,font-size:10px

    ch01["第1章<br/>今天是昨天的明天<br/>🌌 空间站黑塔"]:::mainCh


    %% ── 主线关键任务（每章首尾）──
    m1000101["混乱行至深处"]:::mainTask
    ch01 -.-> m1000101
    m1000304["宇宙安宁片刻"]:::mainTask
    ch01 -.-> m1000304
    m4030001["模拟宇宙•始发测试"]:::mainTask
    ch01 -.-> m4030001

```

## 雅利洛-Ⅵ / 贝洛伯格

```mermaid
flowchart TD

    classDef mainCh   fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef mainTask fill:#42A5F5,stroke:#1E88E5,color:#fff,font-size:10px
    classDef comp     fill:#FF7043,stroke:#E64A19,color:#fff,font-size:10px
    classDef cont     fill:#66BB6A,stroke:#43A047,color:#fff,font-size:10px

    ch02["第2章<br/>于枯索的冬夜里<br/>❄️ 贝洛伯格前期"]:::mainCh
    ch03["第3章<br/>于曈昽的骄阳下<br/>💀 贝洛伯格结局<br/>可可利亚↓布洛妮娅↑"]:::mainCh

    ch02 --> ch03

    %% ── 主线关键任务（每章首尾）──
    m1010002["激「冻」人心的大冒险"]:::mainTask
    ch02 -.-> m1010002
    m1010403["她等待刀尖已经太久"]:::mainTask
    ch02 -.-> m1010403
    m1011001["我们不擅长告别"]:::mainTask
    ch02 -.-> m1011001
    m1011002["在屋外的黑暗中洗涤"]:::mainTask
    ch03 -.-> m1011002
    m1011301["星星是冰冷的玩具"]:::mainTask
    ch03 -.-> m1011301
    m1011503["静静的星河"]:::mainTask
    ch03 -.-> m1011503

    %% ── 同行任务 ──
    c知名不具_ch02["知名不具\n🔓我们不擅长告别"]:::comp
    ch02 ==> c知名不具_ch02
    c阴差阳错_ch02["阴差阳错\n🔓她等待刀尖已经太久"]:::comp
    ch02 ==> c阴差阳错_ch02
    c老矿头的宝贝_ch02["老矿头的宝贝\n🔓躺在铁锈中"]:::comp
    ch02 ==> c老矿头的宝贝_ch02
    c寻药溯源_ch02["寻药溯源\n🔓我们不擅长告别"]:::comp
    ch02 ==> c寻药溯源_ch02
    c小虎克的宝贝_ch02["小虎克的宝贝\n🔓我们不擅长告别"]:::comp
    ch02 ==> c小虎克的宝贝_ch02
    c宇宙幻觉之夜_ch03["宇宙幻觉之夜\n🔓静静的星河"]:::comp
    ch03 ==> c宇宙幻觉之夜_ch03
    c虎克的礼物_ch03["虎克的礼物\n🔓兵士们默默无言"]:::comp
    ch03 ==> c虎克的礼物_ch03
    c难得有情_其一_ch03["难得有情•其一\n🔓静静的星河"]:::comp
    ch03 ==> c难得有情_其一_ch03
    c难得有情_其二_ch03["难得有情•其二\n🔓静静的星河"]:::comp
    ch03 ==> c难得有情_其二_ch03
    c风雪免疫_ch03["风雪免疫\n🔓兵士们默默无言"]:::comp
    ch03 ==> c风雪免疫_ch03
    c时光列车_ch03["时光列车\n🔓静静的星河"]:::comp
    ch03 ==> c时光列车_ch03
    c只是孩子_ch03["只是孩子\n🔓静静的星河"]:::comp
    ch03 ==> c只是孩子_ch03
    c比雪原更遥远_ch03["比雪原更遥远\n🔓静静的星河"]:::comp
    ch03 ==> c比雪原更遥远_ch03
    c我的挚爱_我的血肉_ch03["我的挚爱，我的血肉\n🔓静静的星河"]:::comp
    ch03 ==> c我的挚爱_我的血肉_ch03

    %% ── 开拓续闻 ──
    g庸人自扰_ch03["庸人自扰"]:::cont
    ch03 --> g庸人自扰_ch03
    g天才群星闪耀时_ch03["天才群星闪耀时"]:::cont
    ch03 --> g天才群星闪耀时_ch03

```

## 仙舟「罗浮」前期

```mermaid
flowchart TD

    classDef mainCh   fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef mainTask fill:#42A5F5,stroke:#1E88E5,color:#fff,font-size:10px
    classDef comp     fill:#FF7043,stroke:#E64A19,color:#fff,font-size:10px
    classDef cont     fill:#66BB6A,stroke:#43A047,color:#fff,font-size:10px

    ch04["第4章<br/>乘槎驭风仙窟游<br/>⚓ 仙舟前期"]:::mainCh
    ch05["第5章<br/>云树百丈蔽重楼<br/>🌳 建木灾异"]:::mainCh
    ch06["第6章<br/>劫波渡尽战云收<br/>⚔️ 幻胧被击败"]:::mainCh

    ch04 --> ch05
    ch05 --> ch06

    %% ── 主线关键任务（每章首尾）──
    m1020101["旅进青霄，不速之邀"]:::mainTask
    ch04 -.-> m1020101
    m1020601["迴星周旋，未卜知先"]:::mainTask
    ch04 -.-> m1020601
    m1021101["茸客鸣呦，玉角盘虬"]:::mainTask
    ch04 -.-> m1021101
    m1021201["金鼎灵树，穷途梼杌"]:::mainTask
    ch05 -.-> m1021201
    m1021401["得其雨露，安其壤土"]:::mainTask
    ch05 -.-> m1021401
    m1021601["仙骸成空，大劫有终"]:::mainTask
    ch05 -.-> m1021601
    m1021702["安灵布奠，天清路远"]:::mainTask
    ch06 -.-> m1021702

    %% ── 同行任务 ──
    c譬如朝露_ch04["譬如朝露\n🔓茸客鸣呦，玉角盘虬"]:::comp
    ch04 ==> c譬如朝露_ch04
    c异邦骑士_ch04["异邦骑士\n🔓茸客鸣呦，玉角盘虬"]:::comp
    ch04 ==> c异邦骑士_ch04
    c忧思难忘_ch04["忧思难忘\n🔓茸客鸣呦，玉角盘虬"]:::comp
    ch04 ==> c忧思难忘_ch04
    c霜刃一试_ch04["霜刃一试\n🔓茸客鸣呦，玉角盘虬"]:::comp
    ch04 ==> c霜刃一试_ch04
    c因为我已触碰过天空_ch05["因为我已触碰过天空\n🔓有龙矫矫，其渊渺渺"]:::comp
    ch05 ==> c因为我已触碰过天空_ch05
    c陌生女人的来信_ch05["陌生女人的来信\n🔓有龙矫矫，其渊渺渺"]:::comp
    ch05 ==> c陌生女人的来信_ch05
    c全面回忆_ch06["全面回忆\n🔓安灵布奠，天清路远"]:::comp
    ch06 ==> c全面回忆_ch06
    c龙返其乡_ch06["龙返其乡\n🔓安灵布奠，天清路远"]:::comp
    ch06 ==> c龙返其乡_ch06
    c云无留迹_ch06["云无留迹\n🔓安灵布奠，天清路远"]:::comp
    ch06 ==> c云无留迹_ch06

    %% ── 开拓续闻 ──
    g未来市场_序_ch06["未来市场•序"]:::cont
    ch06 --> g未来市场_序_ch06
    g未来市场_其二_ch06["未来市场•其二"]:::cont
    ch06 --> g未来市场_其二_ch06
    g未来市场_其一_ch06["未来市场•其一"]:::cont
    ch06 --> g未来市场_其一_ch06
    g游园惊梦_ch06["游园惊梦"]:::cont
    ch06 --> g游园惊梦_ch06
    g故客重游_演武天舟_ch06["故客重游，演武天舟"]:::cont
    ch06 --> g故客重游_演武天舟_ch06
    g狴犴吠狂_妙语生香_ch06["狴犴吠狂，妙语生香"]:::cont
    ch06 --> g狴犴吠狂_妙语生香_ch06
    g锷击刃鸣_止戈罢兵_ch06["锷击刃鸣，止戈罢兵"]:::cont
    ch06 --> g锷击刃鸣_止戈罢兵_ch06
    g神锋有归_众议难违_ch06["神锋有归，众议难违"]:::cont
    ch06 --> g神锋有归_众议难违_ch06
    g衔令来使_真意难识_ch06["衔令来使，真意难识"]:::cont
    ch06 --> g衔令来使_真意难识_ch06
    g授剑传行_腾然流星_ch06["授剑传行，腾然流星"]:::cont
    ch06 --> g授剑传行_腾然流星_ch06
    g双生_ch06["双生"]:::cont
    ch06 --> g双生_ch06
    g绥园聚首_其一_ch06["绥园聚首•其一"]:::cont
    ch06 --> g绥园聚首_其一_ch06

```

## 仙舟「罗浮」后期

```mermaid
flowchart TD

    classDef mainCh   fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef mainTask fill:#42A5F5,stroke:#1E88E5,color:#fff,font-size:10px
    classDef comp     fill:#FF7043,stroke:#E64A19,color:#fff,font-size:10px
    classDef cont     fill:#66BB6A,stroke:#43A047,color:#fff,font-size:10px

    ch07["第7章<br/>喧哗与骚动<br/>🗡️ 刃线索 匹诺康尼前奏"]:::mainCh
    ch08["第8章<br/>鸽群中的猫<br/>🕊️ 仙舟尾声"]:::mainCh

    ch07 --> ch08

    %% ── 主线关键任务（每章首尾）──
    m1030101["长日入夜行"]:::mainTask
    ch07 -.-> m1030101
    m1030304["北风的安眠曲"]:::mainTask
    ch07 -.-> m1030304
    m1030801["是谁杀死了…"]:::mainTask
    ch07 -.-> m1030801
    m1030901["天鹅绒里的恶魔"]:::mainTask
    ch08 -.-> m1030901
    m1031601["泄密的心"]:::mainTask
    ch08 -.-> m1031601
    m1032201["行过死荫之地"]:::mainTask
    ch08 -.-> m1032201

    %% ── 同行任务 ──
    c假面双人舞_ch07["假面双人舞\n🔓是谁杀死了…"]:::comp
    ch07 ==> c假面双人舞_ch07

```

## 匹诺康尼

```mermaid
flowchart TD

    classDef mainCh   fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef mainTask fill:#42A5F5,stroke:#1E88E5,color:#fff,font-size:10px
    classDef comp     fill:#FF7043,stroke:#E64A19,color:#fff,font-size:10px
    classDef cont     fill:#66BB6A,stroke:#43A047,color:#fff,font-size:10px

    ch09["第9章<br/>在我们的时代里<br/>🎭 匹诺康尼结局<br/>星期日决战 2.2"]:::mainCh
    ch10["第10章<br/>记忆是梦的开场白<br/>🌙 匹诺康尼 2.0"]:::mainCh
    ch11["第11章<br/>再见，匹诺康尼<br/>🎪 匹诺康尼 2.1"]:::mainCh

    ch09 --> ch10
    ch10 --> ch11

    %% ── 主线关键任务（每章首尾）──
    m1032301["火车大劫案"]:::mainTask
    ch09 -.-> m1032301
    m1032704["奔腾年代"]:::mainTask
    ch09 -.-> m1032704
    m1033102["然后，在第八天…"]:::mainTask
    ch09 -.-> m1033102
    m1033800["树上的灾兆"]:::mainTask
    ch10 -.-> m1033800
    m1033806["树上的灾兆"]:::mainTask
    ch10 -.-> m1033806
    m1033811["终将实现的"]:::mainTask
    ch10 -.-> m1033811
    m1034101["没有被征服的"]:::mainTask
    ch11 -.-> m1034101
    m1034105["浮生若梦"]:::mainTask
    ch11 -.-> m1034105
    m1034109["异乡异客"]:::mainTask
    ch11 -.-> m1034109

    %% ── 开拓续闻 ──
    g一只安达鲁猴_ch11["一只安达鲁猴"]:::cont
    ch11 --> g一只安达鲁猴_ch11
    g四百蕉_ch11["四百蕉"]:::cont
    ch11 --> g四百蕉_ch11
    g落水猴_ch11["落水猴"]:::cont
    ch11 --> g落水猴_ch11
    g发条香蕉_ch11["发条香蕉"]:::cont
    ch11 --> g发条香蕉_ch11
    g死亡蕉社_ch11["死亡蕉社"]:::cont
    ch11 --> g死亡蕉社_ch11
    g踏猴尾_ch11["踏猴尾"]:::cont
    ch11 --> g踏猴尾_ch11
    g阿斯德纳狂想曲_ch11["阿斯德纳狂想曲"]:::cont
    ch11 --> g阿斯德纳狂想曲_ch11
    g命运_驻足梦国之夜_ch11["命运/驻足梦国之夜"]:::cont
    ch11 --> g命运_驻足梦国之夜_ch11
    g命运_归还星之海洋_ch11["命运/归还星之海洋"]:::cont
    ch11 --> g命运_归还星之海洋_ch11
    g命运_重返静默时代_ch11["命运/重返静默时代"]:::cont
    ch11 --> g命运_重返静默时代_ch11

```

## 翁法罗斯

```mermaid
flowchart TD

    classDef mainCh   fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef mainTask fill:#42A5F5,stroke:#1E88E5,color:#fff,font-size:10px
    classDef comp     fill:#FF7043,stroke:#E64A19,color:#fff,font-size:10px
    classDef cont     fill:#66BB6A,stroke:#43A047,color:#fff,font-size:10px

    ch12["第12章<br/>在第八日启程<br/>⏳ 翁法罗斯序章"]:::mainCh
    ch13["第13章<br/>落木逐火英雄纪<br/>🔥 逐火之旅"]:::mainCh
    ch14["第14章<br/>门扉之启，王座之终<br/>👑 凯撒相关"]:::mainCh
    ch15["第15章<br/>走过安眠地的花丛<br/>🌸 翁法罗斯中期"]:::mainCh
    ch16["第16章<br/>在黎明升起时坠落<br/>🔄 轮回显现"]:::mainCh
    ch17["第17章<br/>因为太阳将要毁伤<br/>☀️ 翁法罗斯后期"]:::mainCh
    ch18["第18章<br/>英雄未死之前<br/>🛡️ 决战前"]:::mainCh
    ch19["第19章<br/>于长夜重返大地<br/>🌅 翁法罗斯结局"]:::mainCh

    ch12 --> ch13
    ch13 --> ch14
    ch14 --> ch15
    ch15 --> ch16
    ch16 --> ch17
    ch17 --> ch18
    ch18 --> ch19

    %% ── 主线关键任务（每章首尾）──
    m1036001["所有醒来的人们"]:::mainTask
    ch12 -.-> m1036001
    m1036004["幸存者名为不幸"]:::mainTask
    ch12 -.-> m1036004
    m1036104["听离别轻唱重逢"]:::mainTask
    ch12 -.-> m1036104
    m1040101["银辇啊，迅赴那黑色大地"]:::mainTask
    ch13 -.-> m1040101
    m1040109["悬锋啊，请涤去你的血锈•下"]:::mainTask
    ch13 -.-> m1040109
    m1040118["英雄啊，且握住那枚火种"]:::mainTask
    ch13 -.-> m1040118
    m1040201["纷争啊，伐清湮途的悼惧"]:::mainTask
    ch14 -.-> m1040201
    m1040207["门扉啊，叩声仍激荡梦中"]:::mainTask
    ch14 -.-> m1040207
    m1040213["来路啊，请再度显映往履"]:::mainTask
    ch14 -.-> m1040213
    m1040301["纺锤啊，难纴岁月的经纬"]:::mainTask
    ch15 -.-> m1040301
    m1040306["行者啊，向冥河解缆起航"]:::mainTask
    ch15 -.-> m1040306
    m1040310["魔女的镜中回天"]:::mainTask
    ch15 -.-> m1040310
    m1040401["星空啊，为纷乱千念濯洗"]:::mainTask
    ch16 -.-> m1040401
    m1040411["黎明啊，执耀于全世之终"]:::mainTask
    ch16 -.-> m1040411
    m1040417["黎明啊，执耀于全世之终"]:::mainTask
    ch16 -.-> m1040417
    m1040501["英雄啊，兑现那染血的冀望"]:::mainTask
    ch17 -.-> m1040501
    m1040504["英雄啊，点燃那最初的骄阳"]:::mainTask
    ch17 -.-> m1040504
    m1040506["母亲啊，暌离于冬去春来"]:::mainTask
    ch17 -.-> m1040506
    m1040601["流年啊，渡我漂游千百载"]:::mainTask
    ch18 -.-> m1040601
    m1040608["归风啊，席卷旧尘登云天"]:::mainTask
    ch18 -.-> m1040608
    m1040616["囚人啊，踏过日影见沧溟"]:::mainTask
    ch18 -.-> m1040616
    m1043650["长夜啊，先于黎明前到来"]:::mainTask
    ch19 -.-> m1043650
    m1043662["旅者啊，徘徊中忘却失真"]:::mainTask
    ch19 -.-> m1043662
    m1043677["诸神啊，奏响创世的凯歌"]:::mainTask
    ch19 -.-> m1043677

```

## 二相乐园

```mermaid
flowchart TD

    classDef mainCh   fill:#1565C0,stroke:#0D47A1,color:#fff
    classDef mainTask fill:#42A5F5,stroke:#1E88E5,color:#fff,font-size:10px
    classDef comp     fill:#FF7043,stroke:#E64A19,color:#fff,font-size:10px
    classDef cont     fill:#66BB6A,stroke:#43A047,color:#fff,font-size:10px

    ch20["第20章<br/>成为昨日的明天<br/>🎠 二相乐园序章"]:::mainCh
    ch21["第21章<br/>欢迎来到乐园<br/>🎡 二相乐园"]:::mainCh
    ch22["第22章<br/>献给破晓的失控<br/>🌅 失控"]:::mainCh
    ch23["第23章<br/>如是，众生欢笑不已<br/>😄"]:::mainCh
    ch99["特别章<br/>宇宙均衡<br/>⚖️"]:::mainCh

    ch20 --> ch21
    ch21 --> ch22
    ch22 --> ch23
    ch23 --> ch99

    %% ── 主线关键任务（每章首尾）──
    m1043700["晨曦啊，再抚映遥远地平"]:::mainTask
    ch20 -.-> m1043700
    m1043707["英雄啊，归以凡身向侵晨"]:::mainTask
    ch20 -.-> m1043707
    m1043715["魔女的孤诣课题"]:::mainTask
    ch20 -.-> m1043715
    m1054000["每个人都能成名十五分钟"]:::mainTask
    ch21 -.-> m1054000
    m1054005["幻造艺术的基本原理"]:::mainTask
    ch21 -.-> m1054005
    m1054010["象征交换与侦探"]:::mainTask
    ch21 -.-> m1054010
    m1054100["景观社会及其敌人"]:::mainTask
    ch22 -.-> m1054100
    m1054105["浪子与六翼天使一般神圣"]:::mainTask
    ch22 -.-> m1054105
    m1054111["来自昏暗国度的回音"]:::mainTask
    ch22 -.-> m1054111
    m1054200["观光客的哲学"]:::mainTask
    ch23 -.-> m1054200
    m1054201["在千禧年的阴影下"]:::mainTask
    ch23 -.-> m1054201
    m1054202["超级英雄的道德困境"]:::mainTask
    ch23 -.-> m1054202
    m4020101["「均衡」的试炼•壹"]:::mainTask
    ch99 -.-> m4020101
    m4020107["我们不擅长告别"]:::mainTask
    ch99 -.-> m4020107
    m4020108["「均衡」的试炼•壹"]:::mainTask
    ch99 -.-> m4020108

```

