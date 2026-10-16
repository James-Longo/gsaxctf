"""First-name gender evidence for race-level gender checks.

Many result files carry no gender at all (spreadsheets, hand-typed lists,
mixed "LaLiberte" lists) or carry the wrong one (a header remembered from
the previous race, a filename hint, a parser default). A runner's first
name is independent evidence: a "Girls" race whose names are 95% Ian, Cam
and Luca is a boys race.

Counts are of DISTINCT athletes (first + last name + school), not of
result rows, across every parsed Maine track and cross-country result on
sub5 (2003-2026), so one prolific runner cannot make a name look decisive.
  BOYS / GIRLS   - at least 90% one gender over 5+ athletes (1092 / 1565
                   names): enough to judge a whole race.
  STRICT_BOYS /  - at least 97% over 20+ athletes (212 / 465 names):
  STRICT_GIRLS     enough to overrule one row's printed sex cell.
Names used by both (Taylor, Jordan, Riley, Avery, Charlie ...) are in
neither list and count as no evidence.
"""
import re

BOYS = frozenset("""
    aarav aaron abbas abdi abdifatah abdikadir abdillahi abdirahman abdirashid abdirazak
    abdirizak abdul abdulkadir abdullah abdullahi abe abel abraham abram abshir adam aden adlai
    aedan ahmed aidan aiden aidyn aj ajay alain alan albert alberto alden alec alejandro alek
    alessandro alessio alexande alexander alexandre alexey alexzander alfie alfred alistair
    alister allan allen alvaro alvin alyas amadou amblen ambrose amir amos anders andre andreas
    andrei andres andrew andy angelo angus ansel anselm anthony anton antonio antony archer aric
    arius arlo arron artem arthur aryan asa asher ason aswan att atticus austin ayden bane
    barrak barry bart bashir basilio baxter bayly beau beckett ben benjamin benji bennet bennett
    benny benson bentley bernie bert besic bill billy bj blaine bob bobby bode boden bodhi bodie
    bosco bowen brad braden bradlee bradley brady bradyn braeden braiden bram brandan branden
    brandon brandt brandyn braxton brayden braydon brendan brenden brendon brent brett bretton
    brian briggs brock brodi brodie brody bronson brooks bruce bruno bryan bryant bryce brycen
    bryden bryon bryson buddy byron cade caden caiden cal calder cale caleb calev callum calvin
    cam cameron camren camron can carl carlo carlos carlton carlyle carter cash cason cassius
    cavan cayd cedric chad chae chandler chappy charles chase chester chip chris christian
    christoph christopher chuck cj clay clayton clement cliff clifford clifton clinton clive
    clyde coady codey codie cody cohen colby cole coleman colin collin colson colt colten colton
    conner connor conor conrad cooper corbin cordell corey cormac craig creighton cristian croix
    cullen curran curtis cy cyrus dacota daegan dage dahir dale dalton daly damian damien damon
    damyan dan daniel danny dante darin darren darrin daryl dash dave davi david davin davion
    dawson dayton deacon deagan declan deegan deering demetrius dennis dereck derek derick derik
    derrek derrick deshaun desmond deus deven devvan dexter diego dillan dillion dillon dimitri
    dixon dj dmitri dmitry dom domenic dominic dominick dominik domonic don donald donnie
    donovan dontae doug draco drake draven drew dru duncan dustin dusty dwayne dylan dyllan
    dylon eamon eamonn earl easton eathan eben ed eddie eddy edgar edmund eduardo edwin eero eli
    elias elie elijah elijiah eliot eliott elliott elvis emil emmet emmett emmitt emmons enrico
    ensign enzo ephraim eric erik ernie ethan ethen ethyn eugene evan even everett everette evin
    ewan ezekiel ezra fabian fabrice fahad faisal feleke felix fernando finian finn finnegan
    finnian fionn fischer fletcher florian ford forest forrest foster francesco francois frank
    fred freddie freddy frederick fritz fynn gabe gabriel gage gaige gannon gardner garet garett
    garner garret garrett garrick garrison garte gary gauge gaven gavin gavyn gawain geoff
    geoffrey george gerald gerard gerry giacomo gideon gilbert giles gio giovanni glen golf
    gordon grady graeme graham grant graydon grayson greg gregg gregory greyson griffen griffin
    gryffin gryphon guilherme guillermo gunnar gunner gus gustav hagen haid hale ham hamilton
    hamza hank hans hardy harold harris harrison harry harvey hassan hawn haydn heath hector
    henri henrique henry holden hongtao howie hudson hugo hunter husayn hussain hussein iain ian
    ibrahim ick igor ike ira isaac isaah isaak isacc isaiah isak isiah issac issak ivan izaac
    izaak izaiah izak iziah jabreel jace jack jackson jacob jacobi jacoby jagger jahleel jake
    jakob jakobe jakub jalen jamaal jamal jame james jameson jamison jarad jared jarek jaren
    jarod jaron jarred jarret jarrett jarrod jase jason jasper jax jaxen jaxon jaxson jay jaykob
    jaymes jayson jc jd jeb jed jeff jeffery jeffrey jelani jensen jeremiah jeremy jerome jerry
    jesse jett jim jimmy jin jj joao joaquin job joe joel joeseph joesph joey johan johannes
    john johnathan johnny jon jonah jonas jonathan jonathon jonny jordon jordy jorge jorgen
    joris jose josef joseph josh joshua josiah josue jp jr juan judah jude judson julian julien
    julius junior justin juston justus justyn kade kaden kadin kael kahlil kaiden kaine kale
    kaleb kameron kamron karl karter kasen kayleb kayson keenan kegan keifer keiran keith kellan
    kellen keller kelton ken kenneth kenny kent keon kevin khalil kian kiefer kiernan killian
    king kingston kirby kodi kody kole kolton konnor konor kooper korbin korey kris kristoph
    kristopher kurt kurtis kyle kyler kyran lance landin landon lane larry lars larsen larson
    latrell legeorge leland leo leonard leonardo levi levon lewis lex liam lincoln linus lionel
    lisandro lj long lorenzo louis lowell lt luc luca lucas lucian lucien luis luiz luka lukas
    luke luther lyle mac maccoy mack maddox mahamed makai maksim malachi malcolm malcom manny
    manuel marc marco marcus marek marino mario marius mark markus marshal marshall martin mason
    mat mateo mateus mathew mathias matt mattew matthew matthias mattia matty matyas maverick
    max maxim maximo maximus maxwell maxx melvin merrick micah michael michal micheal midhun
    mike mikey mikhail milan miles milo milos min misael misha mitch mitchel mitchell mohamed
    mohammed moises moritz morris moses mostafa muhammed muktar murphy mustafa myles nash nasir
    nason nat nate nathan nathanael nathanial nathaniel nathen ndrew neal ned neil nelson niall
    nic nicholas nick nickolas nicolas nigel nik nikko niklas niko nikolai nikolas nils noah
    nolan nolen noor norman nyamh obed odin olin oliver omar oren orin orion orrin oscar osh
    oskar osman ostin otis otto owen ozzy pablo pascal pat patric patrick paul pete peter phil
    philip phillip phineas pierre pj porter preston price prince quin quinten quintin quinton
    race rafael raiden raiquan ralph randall randy ransom raphael rasheed rasmus ray raymond
    raynor reed reggie reid remi remington ren reuben revelin rex rhett rhys ricardo riccardo
    ricco rich richard richie rick ricky rico ridge rj roan rob robbie robby robert rocco rogan
    roger roland roman romeo ron ronald ronan ronin ross roy ruben rufino russ russel russell
    rusty ryan ryder rye ryker rylan ryland sabastian sabin sadam saif salah samual samuel sang
    saul sawyer sayer scott scottie seamus sean seb sebastian sebastien sebastion seth shaine
    shammond shamus shane shaun shawn shayne sheldon shep shepard sherman sic silas simeon simon
    skip slade soloman solomon spencer stan stanley staycen stefan stefano stephen steve steven
    stu stuart sullivan sully sylvain sylvester ta tad taka takoda talon tanner tate ted teddy
    temple terrence tevin thaddeus thaden thatcher thayne theo theodore thomas thorin tiger tim
    timmy timothy tj tobey tobias tobin todd tom tomas tommaso tommy tony tor torin trace travis
    trent trenton trever trevor trey tristam tristan triton troy truman trystan tucker turner ty
    tyler tylor tyson uriah vance vaughn vernon victor viktor vince vincent vinnie vinny wade
    walker walter warren wayne wes wesley weston whit wil wilder will willem willi willia
    william willie willis willy wolfgang wyatt xander xavier yannick ylan yle yousef yusuf zac
    zach zachariah zachary zachery zack zackary zackery zain zak zakary zakk zander zane zayne
    zeb zechariah zeke
""".split())

GIRLS = frozenset("""
    aaliyah abagail abbey abbi abbie abbigail abby abi abigael abigail abigal abigale abriana
    acacia acadia ada adalyn addi addie addisyn addy addyson adela adelaide adele adelin adelina
    adeline adelle adelyn adena adia adria adriana adrianna adrienne aela aeryn agnes aida
    ailish aimee ainsley aisha aishwarya aisling aislinn aislyn aiyana alahna alaina alana
    alanna alannah alayna aleah alecia aleesa aleesha aleisha aleksandra alesha alessandra
    alessia aleta alexa alexaiya alexandr alexandra alexandrea alexandria alexia alexis alexus
    alexys alia aliah alice alicia alie alina alisa alisha alison alissa alivia aliya aliyah
    aliza alizah allana allegra alley alli allie allison ally allyson allyssa alma althea aly
    alycia alysa alyse alysha alyson alyssa alyvia amanda amara amaya amber ameila amelia amelie
    amia amina amira amy ana anab anabel anabelle anastasia andi andrea ane angela angelica
    angelina angeline angelique angelyn angie ani ania anika anita anjali ann anna annabel
    annabella annabelle annah annalena annaliese annalise annamaria anne anneka anneliese
    annelise annette annie annika ansley antonia anya aoife april arabella arden aria ariana
    arianna ariel arielle arin arwen aryanna aryn asha ashely ashlee ashleigh ashley ashlyn
    ashlynn asia astrid athena atie aubree aubrie audra audree audrey audrina audry augusta aura
    aurelia aurora autumn ava avah avalon avalyn averi aviana ayanna ayla aysel ayumi azalea
    azaria bailee barbara bayleigh bea beatrice beatriz becca becki becky bekah bella belle
    benedita beth bethanie bethany betsy bettina betty bianca billie blanca bliss blythe bobbi
    bobbie bonnie braelyn brandi brandy brea breanna breanne bree brenda brenna bri briana
    brianna briannah brianne bridget bridgett bridgette brie brielle brigid brigitte brihanna
    brinna brionna bristol britanee britney britta brittani brittany brittney bronte bronwyn
    brook brooke brookelin brookelyn brooklin brooklyn brooklynn bryana bryanna bryanne brylee
    bryleigh brynn brynna brynne cadance cadence cady caelyn cailey cailin cailyn caitie caitlin
    caitlyn caity caleigh cali calla calleigh calli callie callista cami camila camilla camille
    candace cara carey carina carissa carla carley carli carlie carly carmella carmen carol
    carole carolin carolina caroline carolyn carrie caryn carys casandra cassandra cassi cassidy
    cassie cassy castine cat cate caterina catherine cathrine cathryn cathy catie catrina caty
    cayla caylee cayleigh cece cecelia cecile cecilia celena celeste celia celina celine cera
    chanel chantal chantel chantelle charity charlee charlene charli charlott charlotte chastity
    chelsea chelsey chelsie chelsy chenoa cheyanne cheyenne chiara chloe chole chrissy christa
    christiana christie christin christina christine christy chyla cianna cianne ciara ciera
    cierra cindy clair claire clara clare clarissa claudia clementine cleo clio cloe clover codi
    coleen colette colleen connie cora cordelia corina corinne corrin corrine cortney courtney
    cristina crystal cynthia dahlia daisy danae dani danica daniela daniella danielle danika
    danya danyel daphne darby darcy daria darlene dasha davina dawn dawna dayna deanna debbie
    deborah dee deidra deidre deirdre delaina delainey delaney delanie delany delia delilah
    delphi demitria denae denise desirae desiree destinee destiney destiny diana diane dianna
    dina dixie donna dorothy easnadh ebony eden edie edith eileen einat elaina elaine elana
    eleanor eleanora elena eleni elia eliana elianna elin elinor elisa elisabeth elise elissa
    eliza elizabet elizabeth ella elle ellen elli elliana ellianna ellie elly elodie eloise elsa
    elsie elyse elyssa ema emalee emelia emelie emeline emelyn emerald emi emilee emilia emilie
    emily emma emmaline emme emmie emmy emylee erica ericka erika erin eryn esmae esme estella
    estelle ester esther eva evangeline eve evelyn evie evy faith farren fastest fatima fatuma
    fatumo fay faye felicia felicity felisha fern fiona flannery frances francesca francine
    freja freya gabbi gabbie gabby gabi gabriela gabriella gabrielle gabriyah gaby gaetan gaia
    galina gemma geneva genevieve georgia georgiana georgianna georgina gia giana gianna gigi
    gillian gina ginger ginny giovanna giulia giuliana gloria glory graca grace gracelyn gracie
    greta gretchen gwen gwendolyn gwenyth gwyneth hadley haile hailee hailey hailie haleigh
    haley hali halie halle hallee hallie hana hanna hannah harmony harriet hattie hawa hawo
    haylee hayleigh hayley haylie hazel heather heaven heidi helaina helen helena helene hilary
    hilda hillary hodan holland hollie holly hope ida ifrah ila ilana iman imani india inez
    ingrid irene irina iris isa isabel isabela isabell isabella isabelle isadora isis isla
    isobel issy ivory ivy izabel izabela izabella izabelle izzi izzie izzy jacey jackie jacklyn
    jaclyn jacqueline jacquelyn jacqui jada jadah jade jaelyn jaida jaidyn jaimee jalynn jamila
    jana janae jane janell janelle janessa janet janice janna jasmin jasmine jasmyn jayda jayde
    jayla jaylee jaylyn jaymie jazlyn jazlynn jazmin jazmine jazmyn jazmyne jazzy jeanette
    jeannette jemima jen jena jenee jenessa jenn jenna jennah jennasea jenni jennie jennifer
    jenny jerzi jess jessi jessica jessika jessy jewel ji jill jillian joana joanna joanne
    joardin jocelyn jodi jodie joelle johana johanna johannah jolene joli jordyn jorja joselyn
    josephina josephine josie joslyn journey jovanna joy joyce judith judy jules juli julia
    juliana juliann julianna julianne julie juliet juliette june juniper junne justina justine
    kacey kacie kadence kaela kaelyn kahlan kahryn kaia kaila kailee kaileigh kailey kailyn
    kaitlin kaitlyn kaitlynn kaiya kala kalee kaleigh kaley kali kalie kaliyah kalli kallie
    kalyn kammie kara karen kari karin karina karissa karla karlee karli karlie karolina karyn
    kasandra kassandra kassi kassidy kassie kat katarina kate katelin katelyn katelynn katerina
    katey katharine katherin katherine kathleen kathrine kathryn kathy kati katie katja katlyn
    katrina kattie katy katya kaya kaycee kaydance kaydence kayla kaylah kaylee kayleigh kayley
    kayli kaylie kaylin kaylyn kaylynn kaysie kaytlin keara keeley keely keira keisha kelcie
    kelli kellie kelly kellyn kelsea kelsee kelsey kelsi kelsie kelsy kendra kennedy kenzie kera
    keren keri kerigan kerri kerrigan kerstin keya khloe kialeigh kiana kianna kiara kiera
    kierra kiersten kierstin kilee kiley kim kimber kimberly kimmy kinsley kira kirah kiristie
    kirra kirsten kirsti kloe kora kori kortney kosis kourtney krissy krista kristen kristi
    kristie kristin kristina kristine kristy kristyn krysta krystal krysten krystina krystle kya
    kyia kyla kylee kyleigh kylie kyra lacey laci lacie lacy laddy laila lainey lana laney lanie
    lara larissa laura lauralee laurel lauren laurie lauryn layla lea leah leann leanna leanne
    leeann leela leia leighann leila leilei lela lelia lena leona leonie lesley lexi lexia lexie
    lexis lexxie lexy lia liana lianna lianne libby liberty lidia lila lilah lili lilia lilian
    liliana lilianna lilith lilli lillian lilliana lillianna lillie lilly lily lilyana lina
    linda lindsay lindsey lindy lingdong linh linnea linsey lisa lisha liv livia liz liza lizzie
    lizzy lola london lora loran lorelai lorelei loretta lori lorraine lorynn louisa louise
    luana luci lucia lucie lucille lucinda lucy luisa lulu luna lux lydia lyla lylah lyndsay
    lyndsey lynn lynne lyra mabel macey maci macie mackenna mackenzie macy madalyn madalynn
    maddi maddie maddison maddy madelaine madeleine madelin madeline madelyn madelynn madi madie
    madilyn madison madisyn mady madyson mae maegan maelle maeve magali magdalena maggie
    magnolia mahala maia maighread maila mairead maisie maisy maizie maja makala makayla makenna
    makenzie malaya maleah malia mallorie mallory mamie mana mandi mandy mara marah maranda
    maravilha marcella maren margaret margaux margo margot marguerita mari maria mariah mariam
    marian mariana marianna marianne marie mariel marielle marilyn marin marina marion maris
    marisa marissa marjorie markiana marla marlee marlena marley marrissa marta martha martina
    mary mary-kate marya maryan marybeth marykate matilda mattie maude maura maureen mavis
    maxine may maya mazie mckayla mckedra mckenna mckenzie meadow meagan meaghan meara meg megan
    meghan meghann mei mel melanie melina melinda melissa melody mercedes meredith meriah
    merissa mersadie mia micaela michaela michaella micheala michela michele michelle mickayla
    mika mikaela mikala mikayla mikki mila milena millie mimi mina mindy mira miranda miriah
    miriam miski missy misty moira mollie molly monica monique morganne moriah muriel mya myah
    mykayla mykenzie myla myra nadia nadine nala nancy naomi nasro natalee natalia natalie
    natalye natasha natashia nathalie naveah nell nellie nerissa neva nevaeh neve neveah new nia
    nichole nicole nicolette nikki nina noelle nola nora norah nori nyah nyla oceana octavia
    ogechi oksana olga oliva olive olivea olivia olympia oona opal ophelia oriana paige paisley
    pam pamela paris patience patricia patty paula paulina pauline payten pearl penelope penny
    pheobe phoebe phyllis pilar piper pippa polly poppy precious princess priscilla quynh
    rachael racheal rachel rachelle raegan raelyn rahel ramona randi raquel raven rayna reba
    rebecca rebeka rebekah regina rena renee rhianna rhiannon richelle rihan risa rita robyn
    rochelle rohen rori rosa rosalie rose rosemary rosie rothery rowley roxanne roxie ruby ruth
    ruthie ryann ryanne rylee ryleigh rylie saadia sabina sabine sabria sabrina sacopee sade
    sadie safia salena sally salma samantha samara sammi sanaa sandra sanni saoirse saphryn sara
    sarae sarah sarina saskia savana savanah savanna savannah savina sayla scarlet scarlett
    selah selena selina seneca serena serenity shaelyn shaina shakira shalon shania shanika
    shanna shannon sharlene sharon shauna shawna shayla shaylee shaylyn shayna sheila shelby
    shelly sheridan sherry shira shirley shukri shyanne shyla siena sienna siera sierra silvia
    simona simone sinead siobhan skyla sloan sloane smantha sofia sofie soleil sonia sonja sonya
    sophia sophie sopna stacey staci star stefanie stella steph stephanie stephany story sue
    summer sunday sunny susan susanna susannah susie suzanne suzie sydney sydni sydnie sylvia
    sylvie tabarek tabatha tabitha tahlia taija talia tamara tamia tanisha tanya tara taryn
    tasha tatiana tatianna tatum tatumn tatyanna tawnee taya tayla taylar taytum tea teaghan
    tenley teresa terra tess tessa thaovy thea theresa therese tia tiana tianna tiara tiarra
    tierra tiffany tiia tina toia tonya tori torrie tracey traci tracy treasure tressa tricia
    trinity trish trisha trista valentina valerie vanessa veda venessa vera veronica veronika
    vicki vicky victori victoria vika viola violet violette virginia vivi vivian vivienne wendy
    whitney willa willow wynter yana yasmin yolly yulia yvonne zahra zainab zara zaria zeya zina
    zoe zoey zoie zora
""".split())

STRICT_BOYS = frozenset("""
    abdi abe abel aden ahmed alden alec allen angus antonio arthur atticus beau beckett ben bill
    bobby brad braden bradley brady braeden branden brayden braydon brenden brendon brent brett
    brock brody bryan bryson cade caleb calvin carter chad chris clay clayton cole collin colton
    connor cooper corbin curtis damian damien damon dan dave dawson declan derek deven dom
    dominic don doug drake duncan dustin eamon eben emmett eric erik ethan evan ezra felix
    forrest gabe gage gary gavin gideon giovanni grady greyson gus harrison hudson ibrahim isaac
    isiah issac ivan jace jack jacob jakob jalen jarrett jarrod jaxon jaxson jd jeff jeremiah
    jerry jim joe joey johnny jon jonas jonathon josh josiah jude julien kaiden kaleb kameron
    karl keenan ken kenneth kenny kody kurt kyle kyler landon leo levi liam luc lucas lucien
    luis lukas malachi manny mario marshall mason mat mathew matt micheal mike miles mitch
    mohamed nate neil nick noah nolan oliver omar orion owen pablo pat pete phil pj preston
    remington reuben richie ricky rj rob robbie roger roman ronan rylan seamus sebastian seth
    silas simon stephen steve steven sully tanner todd tom tony travis trent trenton trevor troy
    tucker tyson victor vinny walker wayne wes weston will willie wyatt xavier zac zach zachary
    zack zackary zander zeb zeke
""".split())

STRICT_GIRLS = frozenset("""
    aaliyah abbey abbi abbie abby abi abigail acadia ada addie addy adelaide adele adeline
    adrianna aimee ainsley alaina alana alanna alayna alexa alexandra alexia alexis alice alicia
    alisha alison alissa alivia aliyah allie ally allyson alyson alyssa amanda amber amelia amy
    ana angela angelina angie anna annabelle annalise annie annika anya april aria ariana
    arianna arielle ashlee ashleigh ashley ashlyn audrey aurora autumn ava ayla bailee beatrice
    becca bella belle beth bethany bianca breanna bree brianna brianne bridget bridgette brie
    brielle britney brittany brittney brooke brooklyn bryanna brynn caitlin caleigh cali callie
    cara carissa carly carolina caroline carolyn cassandra cassidy cassie catherine cece cecelia
    celia chantal chantel charlotte chelsea chelsey cheyanne cheyenne chloe chrissy christie
    christina christine christy ciara claire clara clare claudia colleen cora corinne corrine
    courtney crystal daisy danica daniela danielle daphne deanna delaney delia desiree destiny
    diana dorothy eileen eleanor elena eliana elisabeth elise eliza elizabeth ella elle ellen
    ellie elsa elsie emelia emilee emilia emilie emily emma emmy erica erika erin esther eva eve
    evelyn evie faith felicity fiona francesca gabby gabriella gabrielle genevieve georgia
    gianna gillian gina gloria grace gracie greta gwen hailee hailey haley halle hallie hana
    hanna hannah hattie haylee hayley hazel heather heidi hilary hillary holly hope iris isabel
    isabella isabelle isla ivy jaclyn jacqueline jada jana janelle jasmin jasmine jazmine jen
    jenn jenna jennie jennifer jenny jessica jill jillian joanna johanna josephine josie julia
    juliana julianna julianne julie justine kaelyn kaila kailey kaitlin kaitlyn kaleigh kallie
    kara karen kari karina kassandra kassidy kat kate katelyn katelynn katharine katherine
    kathleen kathryn katie katrina kaya kayla kaylee kayleigh kaylin keira kellie kelsey kendra
    kenzie kerri kiara kim kimberly kira krissy kristen kristi kristin kristina krystal kyla
    kylee kylie kyra lacey laila lainey laura laurel layla leah leila lena lexie liana libby
    lila lilah lili liliana lillian lilly lily linda lindsey lisa liv liz liza lizzy lorelei
    louise lucia lucy luna lydia lyla lyndsey macy maddy madeleine madeline madelyn madi madilyn
    madison madisyn mae maia maisie makayla makenna mandy mara maranda maren margaret maria
    mariah mariana marie marin marina marisa marissa marta martina mary matilda maureen maya
    mckayla mckenna meaghan meg megan meghan melanie melissa mercedes mia micaela michaela
    michelle mikaela mikala mikayla mindy miranda mollie molly monica mya nadia naomi natalia
    natalie nellie nevaeh nia nichole nicole nikki nina noelle nora norah olivia paige patricia
    penelope phoebe piper rachael rachel rachelle rebecca rebekah renee rhiannon robyn rose
    rosemary rosie ruby ruth sabrina sadie sally samantha sandra sara sarah savanna savannah
    scarlett selena serena shauna shawna shayla shelby sierra silvia siobhan sofia sofie sophia
    sophie stella steph stephanie summer susan susanna sydney sylvia sylvie tabitha tara tasha
    teresa tess tessa theresa tia tiana tianna tiffany tina tori valerie vanessa vera veronica
    victoria violet virginia vivian willa willow zoe zoey
""".split())


def first_name(athlete, last_first=False):
    """'Pierce, Katherine' / 'Katherine Pierce' -> 'katherine'; a bare
    surname gives None. last_first: a list typed "Pierce Katherine"."""
    n = (athlete or '').strip()
    if ',' in n:
        n = n.split(',', 1)[1]
    elif len(n.split()) < 2:
        return None  # a bare surname ("Thomas", "Carl") says nothing
    elif not last_first and re.fullmatch(r"[A-Za-z]\.?", n.split()[0]):
        return None  # an initial: "B Bradley" is not a Bradley
    t = re.findall(r"[A-Za-z][A-Za-z'\-]+", n)
    if last_first and ',' not in (athlete or '') and t:
        return t[-1].lower()
    return t[0].lower() if t else None


def name_gender(athlete, strict=False, last_first=False):
    """'Boys' / 'Girls' when the first name decides it, else None."""
    fn = first_name(athlete, last_first)
    if fn in (STRICT_BOYS if strict else BOYS):
        return 'Boys'
    if fn in (STRICT_GIRLS if strict else GIRLS):
        return 'Girls'
    return None


def last_first_order(rows):
    """True when a list's comma-less names read "Surname Given" (TRAIP's
    "Ek Josephine"): its last words decide far more often than its first."""
    a = b = 0
    for r in rows:
        n = r.get('athlete') or r.get('athlete_name') or ''
        if ',' in n or len(n.split()) < 2:
            continue
        a += name_gender(n) is not None
        b += name_gender(n, last_first=True) is not None
    return b >= 5 and b > 2 * a


def gender_evidence(rows, last_first=None):
    """(boys, girls) counts of decisive first names among result rows."""
    if last_first is None:
        last_first = last_first_order(rows)
    b = g = 0
    for r in rows:
        x = name_gender(r.get('athlete') or r.get('athlete_name'), last_first=last_first)
        if x == 'Boys':
            b += 1
        elif x == 'Girls':
            g += 1
    return b, g
