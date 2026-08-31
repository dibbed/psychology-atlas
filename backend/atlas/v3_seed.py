from .models import (
    Concept,
    ConceptAlias,
    ConceptRelationship,
    ConceptRelationshipSource,
    ConceptSource,
    ConceptSymptom,
    CognitiveDistortionPracticeChoice,
    CognitiveDistortionPracticeItem,
    DailyChallenge,
    DailyChallengeChoice,
    DisorderConcept,
    Flashcard,
    SourceReference,
    Symptom,
)


CONCEPTS = [
    ("panic-attack", "Panic Attack", "حمله پانیک", "clinical", "افزایش ناگهانی ترس یا ناراحتی شدید که در مدت کوتاهی به اوج می‌رسد.", "حمله پانیک یک الگوی زمانی از افزایش سریع ترس همراه با مجموعه‌ای از نشانه‌های جسمانی و شناختی است و به‌تنهایی نام یک اختلال نیست.", "فرد در چند دقیقه دچار تپش قلب، لرزش و ترس شدید از مرگ می‌شود."),
    ("avoidance", "Avoidance", "اجتناب", "behavioral", "دوری‌کردن از موقعیت، فکر یا تجربه‌ای که اضطراب یا ناراحتی ایجاد می‌کند.", "اجتناب می‌تواند ناراحتی را کوتاه‌مدت کاهش دهد، اما در برخی چرخه‌های اضطرابی فرصت یادگیری اصلاحی را محدود و مشکل را حفظ کند.", "دانشجو به‌دلیل ترس از قضاوت، ارائه کلاسی را همیشه لغو می‌کند."),
    ("safety-behaviors", "Safety Behaviors", "رفتارهای ایمنی", "behavioral", "رفتارهایی که فرد برای جلوگیری از پیامد ترسناک یا تحمل موقعیت به آن‌ها تکیه می‌کند.", "رفتارهای ایمنی ممکن است مانع آزمون واقعی باورهای تهدیدآمیز شوند و در برخی مدل‌های شناختی رفتاری به تداوم اضطراب کمک کنند.", "فرد هنگام صحبت در جمع فقط از روی متن می‌خواند تا مبادا مکث کند."),
    ("worry", "Worry", "نگرانی", "cognitive", "زنجیره‌ای از افکار درباره تهدیدها یا پیامدهای منفی آینده.", "نگرانی معمولاً آینده‌محور است و می‌تواند به‌صورت تکراری و دشوار برای کنترل تجربه شود.", "فرد بارها درباره احتمال اشتباه در امتحان فردا فکر می‌کند."),
    ("intrusive-thoughts", "Intrusive Thoughts", "افکار مزاحم", "cognitive", "افکار، تصاویر یا تکانه‌هایی ناخواسته که وارد ذهن می‌شوند و ممکن است ناراحت‌کننده باشند.", "وجود فکر مزاحم به‌خودی‌خود به معنای اختلال نیست؛ اهمیت بالینی به معنا، پاسخ فرد، تکرار و اثر آن بر عملکرد بستگی دارد.", "فکری ناخواسته درباره آلودگی بارها وارد ذهن می‌شود."),
    ("compulsions", "Compulsions", "اعمال اجباری", "behavioral", "رفتار یا عمل ذهنی تکراری که فرد احساس می‌کند باید آن را انجام دهد.", "در الگوهای وسواسی، عمل اجباری اغلب برای کاهش پریشانی یا جلوگیری از پیامد ترسناک انجام می‌شود و کاهش حاصل معمولاً موقتی است.", "فرد برای کاهش اضطراب چندین بار قفل را بررسی می‌کند."),
    ("anhedonia", "Anhedonia", "فقدان لذت", "emotional", "کاهش محسوس علاقه یا توان تجربه لذت از فعالیت‌هایی که قبلاً لذت‌بخش بوده‌اند.", "فقدان لذت یکی از مفاهیم مهم در ارزیابی الگوهای افسردگی است و باید در کنار سایر نشانه‌ها و عملکرد بررسی شود.", "فرد دیگر از موسیقی و دیدار دوستان که قبلاً دوست داشت لذت نمی‌برد."),
    ("rumination", "Rumination", "نشخوار فکری", "cognitive", "فکرکردن تکراری و منفعلانه درباره ناراحتی، علت‌ها یا پیامدهای آن.", "نشخوار فکری معمولاً گذشته یا حالت فعلی را بارها مرور می‌کند و می‌تواند حل مسئله مؤثر را جایگزین کند.", "فرد ساعت‌ها اشتباه یک گفت‌وگوی گذشته را در ذهن مرور می‌کند."),
    ("behavioral-activation", "Behavioral Activation", "فعال‌سازی رفتاری", "treatment", "برنامه‌ریزی تدریجی فعالیت‌های معنادار و تقویت‌کننده برای شکستن چرخه کناره‌گیری و کاهش فعالیت.", "فعال‌سازی رفتاری یک راهبرد ساختاریافته است که ارتباط میان رفتار، محیط و خلق را هدف می‌گیرد و معمولاً با پایش فعالیت همراه می‌شود.", "فرد با برنامه کوچک پیاده‌روی و تماس اجتماعی دوباره فعالیت روزانه را افزایش می‌دهد."),
    ("mania", "Mania", "مانیا", "clinical", "دوره‌ای از افزایش غیرمعمول خلق یا تحریک‌پذیری همراه با افزایش محسوس انرژی و فعالیت که می‌تواند اختلال جدی ایجاد کند.", "در مفهوم مانیا، شدت، تغییر نسبت به خط پایه، پیامد عملکردی و مجموعه نشانه‌های همراه اهمیت دارند.", "فرد چند شب تقریباً نمی‌خوابد، بسیار پرانرژی است و تصمیم‌های پرخطر می‌گیرد."),
    ("hypomania", "Hypomania", "هیپومانیا", "clinical", "دوره‌ای از افزایش خلق یا تحریک‌پذیری و انرژی که از خط پایه متفاوت است اما شدت آن با مانیا کامل یکسان نیست.", "افتراق هیپومانیا از مانیا به شدت، مدت، اختلال عملکرد و پیامدهای دوره وابسته است.", "فرد چند روز انرژی و فعالیت بیشتری دارد و کمتر می‌خوابد، اما اختلال شدید عملکردی ندارد."),
    ("hyperarousal", "Hyperarousal", "برانگیختگی بالا", "clinical", "حالت افزایش برانگیختگی و آمادگی برای واکنش که می‌تواند با گوش‌به‌زنگی و واکنش‌پذیری بالا همراه باشد.", "در زمینه تروما، برانگیختگی بالا می‌تواند بخشی از الگوی تغییرات برانگیختگی و واکنش‌پذیری باشد.", "فرد پس از تروما با صدای کوچک به‌شدت از جا می‌پرد."),
    ("dissociation", "Dissociation", "گسستگی", "clinical", "اختلال یا گسست در تجربه یکپارچه آگاهی، حافظه، هویت یا ادراک.", "گسستگی یک مفهوم طیفی است و باید از تجربه‌های عادی و نیز سایر علت‌های شناختی یا پزشکی تفکیک شود.", "فرد لحظاتی احساس می‌کند محیط غیرواقعی یا دور به نظر می‌رسد."),
    ("rejection-sensitivity", "Rejection Sensitivity", "حساسیت به طرد", "interpersonal", "آمادگی بالا برای انتظار، تشخیص یا واکنش شدید به نشانه‌های طرد.", "حساسیت به طرد یک سازه بین‌فردی است و می‌تواند بر تفسیر موقعیت‌ها و تنظیم هیجان اثر بگذارد.", "پاسخ دیرهنگام یک دوست به‌سرعت به‌عنوان نشانه کنارگذاشته‌شدن تفسیر می‌شود."),
    ("emotion-regulation", "Emotion Regulation", "تنظیم هیجان", "emotional", "فرایندهایی که شدت، مدت یا شیوه تجربه و بیان هیجان را تعدیل می‌کنند.", "تنظیم هیجان شامل راهبردهای متعدد پیش و پس از شکل‌گیری هیجان است و کیفیت آن به زمینه و انعطاف‌پذیری وابسته است.", "فرد پیش از پاسخ تکانشی چند دقیقه مکث می‌کند و هیجان خود را نام‌گذاری می‌کند."),
    ("impulsivity", "Impulsivity", "تکانشگری", "behavioral", "تمایل به عمل سریع با توجه ناکافی به پیامدهای بعدی.", "تکانشگری سازه‌ای چندبعدی است و می‌تواند در زمینه‌های هیجانی، پاداش، برنامه‌ریزی یا مهار پاسخ بررسی شود.", "فرد در اوج هیجان بدون بررسی پیامد تصمیم مالی بزرگی می‌گیرد."),
    ("perfectionism", "Perfectionism", "کمال‌گرایی", "cognitive", "استانداردهای بسیار بالا همراه با ارزیابی سخت‌گیرانه عملکرد خود یا دیگران.", "کمال‌گرایی می‌تواند سازگار یا ناسازگار باشد؛ نگرانی افراطی درباره اشتباه و پیوند ارزش شخصی با عملکرد از جنبه‌های مشکل‌ساز آن است.", "فرد پروژه را تحویل نمی‌دهد چون هیچ نسخه‌ای را به‌اندازه کافی کامل نمی‌داند."),
    ("cognitive-distortions", "Cognitive Distortions", "تحریف‌های شناختی", "cognitive", "الگوهای جهت‌دار و غیرمنعطف در تفسیر اطلاعات که می‌توانند نتیجه‌گیری را از شواهد موجود دور کنند.", "تحریف شناختی برچسبی آموزشی برای الگوهای متداول پردازش و تفسیر است و نباید هر فکر منفی را خودکار تحریف دانست.", "از یک اشتباه کوچک نتیجه گرفته می‌شود که تمام عملکرد شکست بوده است."),
    ("all-or-nothing-thinking", "All-or-Nothing Thinking", "تفکر همه یا هیچ", "cognitive", "دیدن موقعیت‌ها در دو قطب افراطی بدون توجه کافی به طیف میان آن‌ها.", "این الگو کیفیت‌های پیوسته را به دسته‌های مطلق تبدیل می‌کند و می‌تواند ارزیابی عملکرد را سخت‌گیرانه کند.", "اگر نمره‌ام ۲۰ نشود یعنی کاملاً شکست خورده‌ام."),
    ("catastrophizing", "Catastrophizing", "فاجعه‌سازی", "cognitive", "برآورد پیامد یک رویداد به‌عنوان بسیار بدتر یا غیرقابل‌تحمل‌تر از شواهد موجود.", "فاجعه‌سازی معمولاً احتمال یا شدت پیامد منفی و ناتوانی در مقابله با آن را بیش‌برآورد می‌کند.", "اگر در ارائه مکث کنم حتماً آبرویم برای همیشه می‌رود."),
    ("mind-reading", "Mind Reading", "ذهن‌خوانی", "cognitive", "فرض‌کردن اینکه می‌دانیم دیگران چه فکر می‌کنند بدون شواهد کافی.", "ذهن‌خوانی نوعی استنباط درباره حالت ذهنی دیگران است که بدون داده کافی قطعی تلقی می‌شود.", "دوستم ساکت است، پس حتماً فکر می‌کند من بی‌عرضه‌ام."),
    ("automatic-thoughts", "Automatic Thoughts", "افکار خودکار", "cognitive", "افکاری سریع و اغلب کوتاه که در پاسخ به موقعیت ظاهر می‌شوند و ممکن است ابتدا بدیهی به نظر برسند.", "در مدل شناختی، افکار خودکار میان موقعیت، هیجان و رفتار قابل بررسی‌اند و می‌توان اعتبار و کارکرد آن‌ها را آزمود.", "پس از دیدن نمره پایین فوراً فکر می‌کند: من هیچ‌وقت موفق نمی‌شوم."),
    ("core-beliefs", "Core Beliefs", "باورهای هسته‌ای", "cognitive", "باورهای عمیق و کلی درباره خود، دیگران یا جهان که می‌توانند تفسیر تجربه‌ها را جهت دهند.", "باورهای هسته‌ای در مدل‌های شناختی ساختارهای نسبتاً پایدار و کلی‌اند که می‌توانند بر افکار خودکار و قواعد میانی اثر بگذارند.", "باور کلی «من دوست‌داشتنی نیستم» ممکن است تفسیر روابط را جهت دهد."),
    ("exposure", "Exposure", "مواجهه", "treatment", "رویارویی برنامه‌ریزی‌شده و تدریجی با محرک‌ها، موقعیت‌ها یا تجربه‌های ترسناک بدون تکیه کامل بر اجتناب.", "مواجهه یک خانواده از روش‌های رفتاری است که فرصت یادگیری جدید درباره تهدید، تحمل ناراحتی و پیامدهای واقعی را فراهم می‌کند.", "فرد با برنامه از موقعیت‌های اجتماعی کم‌اضطراب شروع و به موقعیت‌های دشوارتر نزدیک می‌شود."),
    ("separation-distress", "Separation Distress", "پریشانی جدایی", "emotional", "ناراحتی و اضطراب قابل توجه هنگام جدایی واقعی یا پیش‌بینی‌شده از فرد دلبستگی.", "پریشانی جدایی یک مفهوم بین‌فردی و هیجانی است و اهمیت بالینی آن به شدت، تناسب رشدی، تداوم و اثر بر عملکرد وابسته است.", "کودک یا بزرگسال هنگام دورشدن از فرد دلبستگی دچار نگرانی شدید و دشواری در ادامه فعالیت روزانه می‌شود."),
    ("difficulty-discarding", "Difficulty Discarding", "دشواری دور ریختن", "behavioral", "دشواری پایدار در کنارگذاشتن یا دورریختن اشیا حتی زمانی که ارزش عملی آن‌ها محدود است.", "در الگوهای احتکار، ناراحتی مرتبط با دورریختن و نیاز ادراک‌شده به نگه‌داشتن اشیا می‌تواند به انباشت و اختلال در استفاده از فضا منجر شود.", "فرد اشیای کم‌استفاده را نگه می‌دارد چون دورریختن آن‌ها اضطراب زیادی ایجاد می‌کند."),
    ("body-focused-repetitive-behaviors", "Body-Focused Repetitive Behaviors", "رفتارهای تکراری متمرکز بر بدن", "behavioral", "رفتارهای تکراری مانند کندن مو یا پوست که روی بدن متمرکزند و کنترل آن‌ها می‌تواند دشوار باشد.", "این اصطلاح یک گروه توصیفی از رفتارهای تکراری متمرکز بر بدن است و برای درک محرک‌ها، عادت، تنش، پیامد جسمانی و تلاش‌های کنترل به کار می‌رود.", "فرد هنگام مطالعه بدون توجه کامل بارها مو یا پوست خود را دستکاری می‌کند."),
    ("cyclical-mood-symptoms", "Cyclical Mood Symptoms", "نشانه‌های خلقی چرخه‌ای", "emotional", "تغییرات هیجانی و جسمانی که به‌صورت منظم با یک چرخه زیستی یا زمانی تکرار می‌شوند.", "در ارزیابی الگوهای چرخه‌ای، ثبت آینده‌نگر زمان شروع و پایان نشانه‌ها برای تشخیص الگوی زمانی اهمیت دارد.", "فرد در چند چرخه متوالی زمان‌بندی مشابهی از تحریک‌پذیری و افت خلق ثبت می‌کند."),
    ("stressor-linked-distress", "Stressor-Linked Distress", "پریشانی مرتبط با عامل استرس‌زا", "clinical", "ناراحتی هیجانی یا رفتاری که ارتباط زمانی روشنی با یک عامل استرس‌زای قابل شناسایی دارد.", "رابطه زمانی با عامل استرس‌زا، شدت ناراحتی، اختلال عملکرد و وجود توضیح‌های جایگزین از ابعاد مهم ارزیابی هستند.", "پس از یک تغییر مهم زندگی، فرد دچار اضطراب و افت عملکرد قابل توجه می‌شود."),
    ("mistrust", "Mistrust", "بی‌اعتمادی", "interpersonal", "انتظار یا تفسیر مکرر رفتار دیگران به‌عنوان غیرقابل اعتماد، آسیب‌زننده یا دارای نیت منفی.", "بی‌اعتمادی می‌تواند در شدت‌ها و زمینه‌های مختلف دیده شود و برای تفسیر آن باید شواهد، انعطاف‌پذیری باور و الگوی بین‌فردی بررسی شود.", "فرد بدون شواهد کافی بارها رفتار همکاران را نشانه قصد آسیب‌زدن تفسیر می‌کند."),
    ("social-detachment", "Social Detachment", "فاصله‌گیری اجتماعی", "interpersonal", "الگوی کاهش درگیری یا علاقه به روابط و تعاملات اجتماعی.", "فاصله‌گیری اجتماعی می‌تواند دلایل متفاوتی داشته باشد؛ تمایل پایین به نزدیکی با اجتناب ناشی از ترس ارزیابی یکسان نیست.", "فرد بیشتر فعالیت‌های انفرادی را ترجیح می‌دهد و تمایل کمی به روابط نزدیک نشان می‌دهد."),
    ("unusual-beliefs", "Unusual Beliefs", "باورهای نامتعارف", "cognitive", "باورها یا تفسیرهایی غیرمعمول که از چارچوب رایج فرهنگی یا بین‌فردی فاصله دارند.", "برای ارزیابی باورهای نامتعارف باید زمینه فرهنگی، میزان قطعیت، انعطاف‌پذیری، تجربه‌های ادراکی و اثر بر عملکرد در نظر گرفته شود.", "فرد برای رویدادهای روزمره معناهای شخصی و غیرمعمولی قائل می‌شود."),
    ("attention-seeking", "Attention Seeking", "جلب توجه", "interpersonal", "رفتارهایی که با هدف یا کارکرد قرارگرفتن در مرکز توجه یا دریافت واکنش دیگران انجام می‌شوند.", "جلب توجه به‌خودی‌خود تشخیص نیست و باید در زمینه انگیزه، الگوی پایدار روابط و پیامدهای عملکردی بررسی شود.", "فرد در موقعیت‌های گروهی مرتب شیوه گفت‌وگو را تغییر می‌دهد تا دوباره مرکز توجه شود."),
    ("grandiosity", "Grandiosity", "بزرگ‌منشی", "cognitive", "ارزیابی اغراق‌شده از اهمیت، توانایی، جایگاه یا استحقاق خود.", "بزرگ‌منشی می‌تواند در زمینه‌های مختلف دیده شود و تفسیر آن به پایداری، شدت، زمینه خلقی و اثر بین‌فردی وابسته است.", "فرد خود را به‌طور پایدار بسیار برتر از دیگران می‌داند و انتظار برخورد ویژه دارد."),
    ("dependency", "Dependency", "وابستگی", "interpersonal", "اتکای زیاد به دیگران برای تصمیم‌گیری، حمایت یا احساس توانایی در اداره موقعیت‌ها.", "وابستگی در یک پیوستار قرار دارد؛ در الگوهای مشکل‌ساز، نیاز به اطمینان و مراقبت می‌تواند استقلال و تصمیم‌گیری را محدود کند.", "فرد برای تصمیم‌های روزمره به تأیید مکرر دیگران نیاز دارد و از تنها ماندن بسیار ناراحت می‌شود."),
]


V4_CONCEPTS = [
    ("discounting-the-positive", "Disqualifying or Discounting the Positive", "بی‌اعتبار کردن نکات مثبت", "cognitive", "کم‌اهمیت یا بی‌اعتبار دانستن شواهد مثبت، حتی وقتی آن شواهد با ارزیابی منفی فرد ناسازگارند.", "در این الگوی شناختی، اطلاعات مثبت پذیرفته نمی‌شود یا به علتی بیرونی و کم‌ارزش نسبت داده می‌شود، در نتیجه ارزیابی منفی بدون اصلاح باقی می‌ماند.", "فرد بعد از تحسین پروژه می‌گوید: «فقط شانس آوردم؛ این موفقیت چیزی درباره توانایی من نشان نمی‌دهد.»"),
    ("emotional-reasoning", "Emotional Reasoning", "استدلال هیجانی", "cognitive", "نتیجه گرفتن درباره واقعیت بر اساس شدت احساس، بدون اینکه احساس به‌تنهایی شواهد کافی باشد.", "در استدلال هیجانی، تجربه هیجانی به‌عنوان مدرک مستقیم برای درستی یک برداشت یا قضاوت تلقی می‌شود.", "فرد می‌گوید: «احساس می‌کنم بی‌کفایتم، پس حتماً واقعاً بی‌کفایتم.»"),
    ("labeling", "Labeling", "برچسب‌زنی", "cognitive", "تبدیل یک رفتار یا خطا به یک برچسب کلی و ثابت درباره خود یا دیگری.", "برچسب‌زنی ارزیابی یک رویداد مشخص را به قضاوت هویتی گسترده تبدیل می‌کند و اطلاعات زمینه‌ای را کم‌رنگ می‌سازد.", "بعد از یک اشتباه می‌گوید: «من یک بازنده‌ام.»"),
    ("magnification-minimization", "Magnification and Minimization", "بزرگ‌نمایی و کوچک‌نمایی", "cognitive", "بیش‌ازحد بزرگ دیدن جنبه‌های منفی یا کم‌اهمیت شمردن شواهد مثبت.", "این الگو وزن اطلاعات را نامتوازن می‌کند؛ شکست یا تهدید بزرگ‌تر و نقاط قوت یا موفقیت کوچک‌تر از شواهد موجود ارزیابی می‌شوند.", "یک نقد کوچک را نشانه شکست جدی می‌داند، اما چند بازخورد مثبت را بی‌اهمیت تلقی می‌کند."),
    ("mental-filter", "Mental Filter", "فیلتر ذهنی", "cognitive", "تمرکز انتخابی بر بخش منفی تجربه و نادیده گرفتن سایر اطلاعات مرتبط.", "در فیلتر ذهنی یا انتزاع انتخابی، یک جزء منفی از زمینه بزرگ‌تر جدا می‌شود و بر ارزیابی کل تجربه غالب می‌شود.", "از میان چند بازخورد مثبت و یک نقد، فقط همان نقد را به خاطر می‌سپارد و کل عملکرد را بد ارزیابی می‌کند."),
    ("overgeneralization", "Overgeneralization", "تعمیم افراطی", "cognitive", "ساختن نتیجه‌ای گسترده از یک یا چند تجربه محدود.", "تعمیم افراطی از داده محدود یک قاعده کلی درباره آینده، خود یا روابط می‌سازد، بدون اینکه دامنه شواهد برای چنین نتیجه‌ای کافی باشد.", "چون در یک مهمانی معذب بوده نتیجه می‌گیرد: «من هیچ‌وقت نمی‌توانم دوست پیدا کنم.»"),
    ("personalization", "Personalization", "شخصی‌سازی", "cognitive", "نسبت دادن مسئولیت یا علت یک رویداد به خود بدون شواهد کافی درباره نقش واقعی فرد.", "در شخصی‌سازی، سهم عوامل دیگر یا ابهام موقعیت کم‌رنگ می‌شود و فرد خود را علت رویدادی می‌داند که شواهد کافی برای این نسبت وجود ندارد.", "همکارش کوتاه جواب می‌دهد و فوراً نتیجه می‌گیرد: «حتماً من کاری کرده‌ام که ناراحت شده.»"),
    ("should-must-statements", "Should and Must Statements", "بایدها و الزام‌های خشک", "cognitive", "به‌کارگیری قواعد سخت و مطلق درباره اینکه خود یا دیگران چگونه باید رفتار کنند.", "این الگو ترجیح یا هدف را به الزام انعطاف‌ناپذیر تبدیل می‌کند و می‌تواند خطا یا تفاوت را به‌صورت غیرمتناسب ارزیابی کند.", "فرد می‌گوید: «من باید همیشه بهترین عملکردم را داشته باشم؛ اشتباه کردن غیرقابل قبول است.»"),
    ("tunnel-vision", "Tunnel Vision", "دید تونلی", "cognitive", "دیدن عمدتاً جنبه‌های منفی یک فرد یا موقعیت و از دست دادن تصویر متوازن‌تر.", "در دید تونلی، توجه و ارزیابی روی یک مجموعه محدود از اطلاعات نامطلوب قفل می‌شود و اطلاعات ناسازگار با آن کمتر وارد قضاوت می‌شوند.", "در ارزیابی یک استاد فقط موارد آزاردهنده را می‌بیند و هیچ رفتار مفید یا خنثی را در نظر نمی‌گیرد."),
]


CONCEPT_ENRICHMENT = {
    "panic-attack": {"domain": "psychopathology"},
    "avoidance": {"domain": "behavioral_science"},
    "safety-behaviors": {"domain": "cbt"},
    "worry": {"domain": "cognitive_psychology"},
    "intrusive-thoughts": {"domain": "cognitive_psychology"},
    "compulsions": {"domain": "psychopathology"},
    "anhedonia": {"domain": "psychopathology"},
    "rumination": {"domain": "cognitive_psychology"},
    "behavioral-activation": {"domain": "cbt"},
    "mania": {"domain": "psychopathology"},
    "hypomania": {"domain": "psychopathology"},
    "hyperarousal": {"domain": "psychopathology"},
    "dissociation": {"domain": "psychopathology"},
    "rejection-sensitivity": {"domain": "interpersonal"},
    "emotion-regulation": {"domain": "emotion"},
    "impulsivity": {"domain": "behavioral_science"},
    "perfectionism": {"domain": "cognitive_psychology"},
    "cognitive-distortions": {"domain": "cbt"},
    "automatic-thoughts": {"domain": "cbt"},
    "core-beliefs": {"domain": "cbt"},
    "exposure": {"domain": "cbt"},
    "separation-distress": {"domain": "emotion"},
    "difficulty-discarding": {"domain": "psychopathology"},
    "body-focused-repetitive-behaviors": {"domain": "psychopathology"},
    "cyclical-mood-symptoms": {"domain": "psychopathology"},
    "stressor-linked-distress": {"domain": "psychopathology"},
    "mistrust": {"domain": "interpersonal"},
    "social-detachment": {"domain": "interpersonal"},
    "unusual-beliefs": {"domain": "psychopathology"},
    "attention-seeking": {"domain": "interpersonal"},
    "grandiosity": {"domain": "psychopathology"},
    "dependency": {"domain": "interpersonal"},
}

DISTORTION_DETAILS = {
    "all-or-nothing-thinking": {"counterexample": "عملکرد می‌تواند ترکیبی از نقاط قوت و ضعف باشد؛ یک نتیجه کمتر از ایده‌آل مساوی شکست کامل نیست.", "recognition_cues": "واژه‌های مطلق مانند همیشه، هرگز، کامل، شکست کامل یا فقط دو گزینه افراطی.", "common_confusions": "با کمال‌گرایی همپوشانی دارد، اما یکی نیست؛ کمال‌گرایی می‌تواند استاندارد بالا باشد، در حالی که همه یا هیچ نحوه دسته‌بندی نتیجه است."},
    "catastrophizing": {"counterexample": "ممکن است نتیجه ناخوشایند باشد، اما شدت، احتمال و توان مقابله باید جداگانه با شواهد سنجیده شوند.", "recognition_cues": "پیش‌بینی بدترین پیامد به‌عنوان نتیجه محتمل یا غیرقابل تحمل.", "common_confusions": "با نگرانی تفاوت دارد؛ نگرانی فرایند تکراری آینده‌محور است، اما فاجعه‌سازی نوع خاصی از ارزیابی پیامد است."},
    "mind-reading": {"counterexample": "می‌توان چند توضیح ممکن برای رفتار طرف مقابل در نظر گرفت و برای نتیجه قطعی به شواهد بیشتری نیاز داشت.", "recognition_cues": "جملاتی مثل «حتماً فکر می‌کند...» یا نتیجه‌گیری قطعی درباره ذهن دیگران بدون داده مستقیم.", "common_confusions": "با حساسیت به طرد یکی نیست؛ حساسیت به طرد یک سازه بین‌فردی گسترده‌تر است و ذهن‌خوانی یک الگوی استنباط شناختی است."},
    "discounting-the-positive": {"counterexample": "موفقیت یا بازخورد مثبت را می‌توان به‌عنوان بخشی از کل شواهد در نظر گرفت، حتی اگر کامل یا قطعی نباشد.", "recognition_cues": "عبارت‌هایی مانند «این حساب نیست»، «فقط شانس بود» یا حذف نظام‌مند شواهد مثبت.", "common_confusions": "با کوچک‌نمایی نزدیک است؛ بی‌اعتبار کردن مثبت بیشتر اعتبار شواهد مثبت را رد می‌کند."},
    "emotional-reasoning": {"counterexample": "احساس مهم است، اما برای نتیجه‌گیری درباره واقعیت باید شواهد مستقل هم بررسی شوند.", "recognition_cues": "ساختار «چون احساس می‌کنم X، پس X واقعیت دارد».", "common_confusions": "با هیجان شدید یکی نیست؛ تحریف در استنتاج از احساس رخ می‌دهد، نه صرف داشتن احساس."},
    "labeling": {"counterexample": "به‌جای برچسب کلی، رفتار یا رویداد مشخص توصیف می‌شود: «در این کار اشتباه کردم» نه «من بازنده‌ام».", "recognition_cues": "برچسب‌های هویتی و کلی بر اساس رفتار محدود.", "common_confusions": "با تعمیم افراطی مرتبط است، اما برچسب‌زنی معمولاً نتیجه را به هویت یا ارزش کلی تبدیل می‌کند."},
    "magnification-minimization": {"counterexample": "وزن شواهد مثبت و منفی متناسب با اهمیت واقعی هرکدام سنجیده می‌شود.", "recognition_cues": "بزرگ کردن خطاها یا تهدیدها همراه با کوچک شمردن موفقیت‌ها یا منابع مقابله.", "common_confusions": "با فاجعه‌سازی همپوشانی دارد؛ فاجعه‌سازی بیشتر روی پیامد بسیار بد تمرکز دارد."},
    "mental-filter": {"counterexample": "کل مجموعه اطلاعات، از جمله داده‌های مثبت، منفی و خنثی، در ارزیابی لحاظ می‌شود.", "recognition_cues": "یک جز منفی همه تصویر را تحت‌الشعاع قرار می‌دهد.", "common_confusions": "با دید تونلی نزدیک است؛ فیلتر ذهنی اغلب روی یک جزء انتخابی متمرکز می‌شود، دید تونلی می‌تواند نگاه منفی گسترده‌تری ایجاد کند."},
    "overgeneralization": {"counterexample": "یک تجربه محدود فقط درباره همان موقعیت اطلاعات می‌دهد مگر شواهد بیشتری برای قاعده کلی وجود داشته باشد.", "recognition_cues": "نتیجه‌های کلی مثل «همیشه»، «هیچ‌وقت»، «همه» از نمونه‌های محدود.", "common_confusions": "با همه یا هیچ متفاوت است؛ تعمیم افراطی دامنه نتیجه را گسترش می‌دهد، همه یا هیچ طیف را به دو قطب تبدیل می‌کند."},
    "personalization": {"counterexample": "نقش خود، نقش دیگران و عوامل موقعیتی جداگانه بررسی می‌شوند و مسئولیت فقط با شواهد نسبت داده می‌شود.", "recognition_cues": "فرض خودکار اینکه رفتار یا رویداد بیرونی به خاطر من رخ داده است.", "common_confusions": "با مسئولیت‌پذیری سالم یکی نیست؛ مسئله نسبت دادن علت بدون شواهد کافی است."},
    "should-must-statements": {"counterexample": "ترجیح و ارزش می‌تواند به زبان انعطاف‌پذیر بیان شود: «دوست دارم خوب عمل کنم، اما اشتباه هم ممکن است.»", "recognition_cues": "باید، نباید، حتماً، همیشه باید، غیرقابل قبول است.", "common_confusions": "داشتن استاندارد یا ارزش به‌خودی‌خود تحریف نیست؛ سختی و مطلق‌بودن قاعده مهم است."},
    "tunnel-vision": {"counterexample": "برای ارزیابی متوازن، شواهد ناسازگار با برداشت اولیه نیز عمداً جست‌وجو و بررسی می‌شوند.", "recognition_cues": "دیدن تقریباً فقط جنبه‌های منفی یک فرد یا موقعیت.", "common_confusions": "با فیلتر ذهنی نزدیک است و مرز آن‌ها در منابع آموزشی می‌تواند همپوشان باشد."},
}

CONCEPT_ALIASES = [
    ("catastrophizing", "Fortune Telling", "en", "alternative"),
    ("catastrophizing", "پیش‌گویی منفی", "fa", "alternative"),
    ("mental-filter", "Selective Abstraction", "en", "alternative"),
    ("mental-filter", "انتزاع انتخابی", "fa", "alternative"),
    ("discounting-the-positive", "Disqualifying the Positive", "en", "alternative"),
    ("discounting-the-positive", "Discounting the Positive", "en", "alternative"),
    ("should-must-statements", "Should Statements", "en", "alternative"),
    ("should-must-statements", "Must Statements", "en", "alternative"),
]

CONCEPT_SYMPTOMS = [
    ("avoidance", "avoidance", "manifestation"),
    ("intrusive-thoughts", "intrusive-thoughts", "manifestation"),
    ("compulsions", "compulsions", "manifestation"),
    ("anhedonia", "anhedonia", "manifestation"),
    ("hyperarousal", "hyperarousal", "manifestation"),
    ("dissociation", "dissociation", "manifestation"),
    ("rejection-sensitivity", "rejection-sensitivity", "manifestation"),
    ("impulsivity", "impulsivity", "manifestation"),
    ("perfectionism", "perfectionism", "manifestation"),
    ("mistrust", "mistrust", "manifestation"),
    ("social-detachment", "social-detachment", "manifestation"),
    ("unusual-beliefs", "unusual-beliefs", "manifestation"),
    ("attention-seeking", "attention-seeking", "manifestation"),
    ("grandiosity", "grandiosity", "manifestation"),
    ("dependency", "dependency", "manifestation"),
]


CONCEPT_RELATIONS = [
    ("all-or-nothing-thinking", "cognitive-distortions", "part_of", "تفکر همه یا هیچ یکی از الگوهای رایج آموزش‌داده‌شده در مجموعه تحریف‌های شناختی است."),
    ("catastrophizing", "cognitive-distortions", "part_of", "فاجعه‌سازی یکی از الگوهای رایج تفسیر جهت‌دار پیامدهاست."),
    ("mind-reading", "cognitive-distortions", "part_of", "ذهن‌خوانی نمونه‌ای از نتیجه‌گیری درباره ذهن دیگران بدون شواهد کافی است."),
    ("core-beliefs", "automatic-thoughts", "influences", "باورهای کلی می‌توانند احتمال و محتوای افکار خودکار را جهت دهند."),
    ("automatic-thoughts", "cognitive-distortions", "related", "افکار خودکار ممکن است شامل تحریف باشند، اما هر فکر خودکار الزاماً تحریف‌شده نیست."),
    ("worry", "rumination", "contrasts", "نگرانی معمولاً آینده‌محورتر و نشخوار فکری بیشتر حول گذشته یا حالت فعلی است، هرچند همپوشانی دارند."),
    ("intrusive-thoughts", "compulsions", "influences", "در برخی چرخه‌های وسواسی، معنای تهدیدآمیز فکر مزاحم می‌تواند عمل اجباری را برانگیزد."),
    ("avoidance", "safety-behaviors", "related", "هر دو می‌توانند از مواجهه کامل با موقعیت ترسناک یا آزمون باورهای تهدیدآمیز جلوگیری کنند."),
    ("exposure", "avoidance", "contrasts", "مواجهه به‌طور هدفمند حرکت به‌سمت تجربه ترسناک را در برابر الگوی اجتناب تمرین می‌کند."),
    ("rejection-sensitivity", "emotion-regulation", "influences", "برداشت سریع از طرد می‌تواند شدت هیجان و نیاز به تنظیم آن را افزایش دهد."),
    ("emotion-regulation", "impulsivity", "related", "مشکلات تنظیم هیجان می‌توانند در برخی زمینه‌ها با پاسخ‌های تکانشی همراه شوند."),
    ("mania", "hypomania", "contrasts", "هر دو با افزایش انرژی و تغییر خلق مرتبط‌اند، اما شدت و پیامد عملکردی برای افتراق مهم است."),
    ("rumination", "anhedonia", "related", "نشخوار فکری و کاهش درگیری با فعالیت‌های تقویت‌کننده می‌توانند در الگوهای افسردگی همزمان دیده شوند."),
    ("behavioral-activation", "rumination", "contrasts", "فعال‌سازی رفتاری توجه را از درگیری منفعلانه با فکر به اقدام برنامه‌ریزی‌شده و معنادار منتقل می‌کند."),
]


DISORDER_CONCEPTS = [
    ("panic-disorder", "panic-attack", "core"), ("panic-disorder", "avoidance", "maintaining"), ("panic-disorder", "safety-behaviors", "maintaining"), ("panic-disorder", "exposure", "treatment"),
    ("generalized-anxiety-disorder", "worry", "core"), ("generalized-anxiety-disorder", "avoidance", "associated"),
    ("social-anxiety-disorder", "avoidance", "core"), ("social-anxiety-disorder", "safety-behaviors", "maintaining"), ("social-anxiety-disorder", "mind-reading", "associated"), ("social-anxiety-disorder", "rejection-sensitivity", "associated"), ("social-anxiety-disorder", "exposure", "treatment"),
    ("specific-phobia", "avoidance", "core"), ("specific-phobia", "exposure", "treatment"), ("agoraphobia", "avoidance", "core"), ("agoraphobia", "exposure", "treatment"),
    ("obsessive-compulsive-disorder", "intrusive-thoughts", "core"), ("obsessive-compulsive-disorder", "compulsions", "core"), ("obsessive-compulsive-disorder", "avoidance", "maintaining"), ("obsessive-compulsive-disorder", "exposure", "treatment"),
    ("major-depressive-disorder", "anhedonia", "core"), ("major-depressive-disorder", "rumination", "maintaining"), ("major-depressive-disorder", "automatic-thoughts", "associated"), ("major-depressive-disorder", "core-beliefs", "associated"), ("major-depressive-disorder", "behavioral-activation", "treatment"),
    ("persistent-depressive-disorder", "anhedonia", "associated"), ("persistent-depressive-disorder", "rumination", "associated"),
    ("bipolar-i-disorder", "mania", "core"), ("bipolar-ii-disorder", "hypomania", "core"), ("bipolar-ii-disorder", "anhedonia", "associated"), ("cyclothymic-disorder", "hypomania", "differential"),
    ("post-traumatic-stress-disorder", "hyperarousal", "core"), ("post-traumatic-stress-disorder", "dissociation", "associated"), ("post-traumatic-stress-disorder", "avoidance", "core"), ("post-traumatic-stress-disorder", "exposure", "treatment"),
    ("acute-stress-disorder", "dissociation", "associated"), ("acute-stress-disorder", "hyperarousal", "associated"),
    ("borderline-personality-disorder", "emotion-regulation", "core"), ("borderline-personality-disorder", "rejection-sensitivity", "associated"), ("borderline-personality-disorder", "impulsivity", "associated"),
    ("avoidant-personality-disorder", "rejection-sensitivity", "core"), ("avoidant-personality-disorder", "avoidance", "core"),
    ("obsessive-compulsive-personality-disorder", "perfectionism", "core"),
    ("body-dysmorphic-disorder", "safety-behaviors", "associated"), ("body-dysmorphic-disorder", "intrusive-thoughts", "associated"),
    ("separation-anxiety-disorder", "separation-distress", "core"), ("separation-anxiety-disorder", "worry", "associated"), ("separation-anxiety-disorder", "avoidance", "associated"),
    ("hoarding-disorder", "difficulty-discarding", "core"),
    ("trichotillomania", "body-focused-repetitive-behaviors", "core"), ("excoriation-disorder", "body-focused-repetitive-behaviors", "core"),
    ("premenstrual-dysphoric-disorder", "cyclical-mood-symptoms", "core"), ("premenstrual-dysphoric-disorder", "emotion-regulation", "associated"),
    ("adjustment-disorder", "stressor-linked-distress", "core"), ("adjustment-disorder", "emotion-regulation", "associated"),
    ("paranoid-personality-disorder", "mistrust", "core"),
    ("schizoid-personality-disorder", "social-detachment", "core"),
    ("schizotypal-personality-disorder", "unusual-beliefs", "core"), ("schizotypal-personality-disorder", "social-detachment", "associated"),
    ("antisocial-personality-disorder", "impulsivity", "associated"),
    ("histrionic-personality-disorder", "attention-seeking", "core"), ("histrionic-personality-disorder", "emotion-regulation", "associated"),
    ("narcissistic-personality-disorder", "grandiosity", "core"), ("narcissistic-personality-disorder", "rejection-sensitivity", "associated"),
    ("dependent-personality-disorder", "dependency", "core"), ("dependent-personality-disorder", "rejection-sensitivity", "associated"),
]


FLASHCARDS = [
    ("fc-panic-attack", "حمله پانیک چیست؟", "افزایش ناگهانی ترس یا ناراحتی شدید که در مدت کوتاهی به اوج می‌رسد؛ به‌خودی‌خود نام یک اختلال نیست.", "panic-attack", "panic-disorder"),
    ("fc-avoidance", "اجتناب چگونه می‌تواند چرخه اضطراب را حفظ کند؟", "با کاهش کوتاه‌مدت اضطراب، فرصت آزمون تهدید و یادگیری اصلاحی را محدود می‌کند.", "avoidance", None),
    ("fc-safety", "رفتار ایمنی چیست؟", "رفتاری برای پیشگیری از پیامد ترسناک یا تحمل موقعیت که ممکن است آزمون واقعی باور تهدیدآمیز را محدود کند.", "safety-behaviors", None),
    ("fc-worry", "تفاوت ساده نگرانی با نشخوار فکری چیست؟", "نگرانی معمولاً آینده‌محورتر است؛ نشخوار بیشتر گذشته یا ناراحتی فعلی را بارها مرور می‌کند.", "worry", "generalized-anxiety-disorder"),
    ("fc-intrusive", "فکر مزاحم به‌تنهایی چه چیزی را ثابت نمی‌کند؟", "وجود فکر مزاحم به‌تنهایی وجود اختلال را ثابت نمی‌کند؛ پاسخ فرد و اثر عملکردی مهم‌اند.", "intrusive-thoughts", "obsessive-compulsive-disorder"),
    ("fc-compulsion", "عمل اجباری در چرخه OCD چه نقشی دارد؟", "اغلب برای کاهش پریشانی یا جلوگیری از پیامد ترسناک انجام می‌شود و کاهش اضطراب معمولاً موقتی است.", "compulsions", "obsessive-compulsive-disorder"),
    ("fc-anhedonia", "Anhedonia یعنی چه؟", "کاهش محسوس علاقه یا توان تجربه لذت از فعالیت‌هایی که قبلاً لذت‌بخش بوده‌اند.", "anhedonia", "major-depressive-disorder"),
    ("fc-rumination", "نشخوار فکری چیست؟", "فکرکردن تکراری و منفعلانه درباره ناراحتی، علت‌ها یا پیامدهای آن بدون حرکت مؤثر به سمت حل مسئله.", "rumination", "major-depressive-disorder"),
    ("fc-ba", "هدف ساده فعال‌سازی رفتاری چیست؟", "افزایش تدریجی فعالیت‌های معنادار و تقویت‌کننده برای شکستن چرخه کناره‌گیری و کاهش فعالیت.", "behavioral-activation", "major-depressive-disorder"),
    ("fc-mania", "در افتراق مانیا و هیپومانیا چه بعدی مهم است؟", "شدت، اختلال عملکرد و پیامدهای دوره در کنار الگوی نشانه‌ها.", "mania", "bipolar-i-disorder"),
    ("fc-hypomania", "هیپومانیا چه تفاوت کلی با مانیا دارد؟", "افزایش خلق و انرژی وجود دارد اما شدت و پیامد عملکردی آن با مانیا کامل یکسان نیست.", "hypomania", "bipolar-ii-disorder"),
    ("fc-hyperarousal", "برانگیختگی بالا پس از تروما می‌تواند چگونه دیده شود؟", "مثلاً گوش‌به‌زنگی، واکنش از جا پریدن و واکنش‌پذیری بالا.", "hyperarousal", "post-traumatic-stress-disorder"),
    ("fc-dissociation", "گسستگی چیست؟", "گسست در تجربه یکپارچه آگاهی، حافظه، هویت یا ادراک که شدت و شکل‌های متفاوتی دارد.", "dissociation", None),
    ("fc-rejection", "حساسیت به طرد چیست؟", "انتظار یا تشخیص سریع طرد و واکنش شدید به نشانه‌های احتمالی کنارگذاشته‌شدن.", "rejection-sensitivity", None),
    ("fc-regulation", "تنظیم هیجان به چه معناست؟", "فرایندهایی که شدت، مدت یا شیوه تجربه و بیان هیجان را تعدیل می‌کنند.", "emotion-regulation", None),
    ("fc-impulsivity", "تعریف ساده تکانشگری چیست؟", "عمل سریع با توجه ناکافی به پیامدهای بعدی.", "impulsivity", None),
    ("fc-perfectionism", "چه زمانی کمال‌گرایی می‌تواند مشکل‌ساز شود؟", "وقتی استانداردهای سخت‌گیرانه، ترس از اشتباه یا پیوند ارزش شخصی با عملکرد باعث اختلال و انعطاف‌ناپذیری شوند.", "perfectionism", "obsessive-compulsive-personality-disorder"),
    ("fc-distortions", "تحریف شناختی چیست؟", "الگوی جهت‌دار و غیرمنعطف در تفسیر اطلاعات که نتیجه‌گیری را از شواهد موجود دور می‌کند.", "cognitive-distortions", None),
    ("fc-all-or-nothing", "«اگر ۲۰ نگیرم کاملاً شکست خورده‌ام» نمونه چیست؟", "تفکر همه یا هیچ.", "all-or-nothing-thinking", None),
    ("fc-catastrophizing", "«اگر مکث کنم آبرویم برای همیشه می‌رود» نمونه چیست؟", "فاجعه‌سازی.", "catastrophizing", None),
    ("fc-mind-reading", "«او ساکت است پس حتماً من را بی‌عرضه می‌داند» نمونه چیست؟", "ذهن‌خوانی.", "mind-reading", None),
    ("fc-automatic", "افکار خودکار چه ویژگی دارند؟", "سریع و کوتاه در پاسخ به موقعیت ظاهر می‌شوند و ممکن است ابتدا بدیهی به نظر برسند.", "automatic-thoughts", None),
    ("fc-core-beliefs", "باور هسته‌ای چیست؟", "باور عمیق و کلی درباره خود، دیگران یا جهان که می‌تواند تفسیر تجربه‌ها را جهت دهد.", "core-beliefs", None),
    ("fc-exposure", "مواجهه در یک جمله چیست؟", "رویارویی برنامه‌ریزی‌شده با محرک یا تجربه ترسناک برای ایجاد فرصت یادگیری جدید به جای تکیه کامل بر اجتناب.", "exposure", None),
    ("fc-panic-vs-gad", "Panic Disorder و GAD در یک خط چه تفاوتی دارند؟", "پانیک با حملات ناگهانی برجسته است؛ GAD با نگرانی گسترده و پایدار درباره چند حوزه.", None, "panic-disorder"),
    ("fc-ocd-vs-ocpd", "OCD و OCPD یکی هستند؟", "نه. OCD حول وسواس و اجبار است؛ OCPD الگوی شخصیتی پایدار کمال‌گرایی، نظم و کنترل است.", None, "obsessive-compulsive-disorder"),
    ("fc-bipolar-i-ii", "تفاوت آموزشی مهم Bipolar I و II چیست؟", "وجود سابقه مانیا کامل در Bipolar I؛ Bipolar II با هیپومانیا و دوره‌های افسردگی تعریف می‌شود.", None, "bipolar-i-disorder"),
    ("fc-ptsd-asd", "PTSD و Acute Stress Disorder در چه بعدی مهم افتراق دارند؟", "زمان‌بندی نشانه‌ها پس از تروما یکی از ابعاد مهم افتراق است.", None, "post-traumatic-stress-disorder"),
    ("fc-social-avoidant", "Social Anxiety و Avoidant PD چرا ممکن است اشتباه شوند؟", "هر دو می‌توانند ترس از ارزیابی و اجتناب اجتماعی داشته باشند؛ در شخصیت اجتنابی الگو فراگیرتر و پایدارتر است.", None, "social-anxiety-disorder"),
    ("fc-depression-bipolar", "در ارزیابی افسردگی چرا سابقه خلق بالا مهم است؟", "برای بررسی احتمال طیف دوقطبی و جلوگیری از تفسیر ناقص الگوی خلق.", None, "major-depressive-disorder"),
    ("fc-separation-distress", "پریشانی جدایی به چه معناست؟", "اضطراب یا ناراحتی قابل توجه هنگام جدایی واقعی یا پیش‌بینی‌شده از فرد دلبستگی.", "separation-distress", "separation-anxiety-disorder"),
    ("fc-discarding", "مفهوم محوری در اختلال احتکار چیست؟", "دشواری پایدار در دور ریختن یا جداشدن از اشیا همراه با ناراحتی و نیاز ادراک‌شده به نگه‌داشتن آن‌ها.", "difficulty-discarding", "hoarding-disorder"),
    ("fc-bfrb", "رفتارهای تکراری متمرکز بر بدن به چه گروهی اشاره دارد؟", "رفتارهای تکراری مانند کندن مو یا پوست که روی بدن متمرکزند و کنترل آن‌ها می‌تواند دشوار باشد.", "body-focused-repetitive-behaviors", None),
    ("fc-cyclical-mood", "برای بررسی نشانه‌های خلقی چرخه‌ای چه چیزی مهم است؟", "ثبت زمان شروع و پایان نشانه‌ها در چند چرخه برای دیدن الگوی زمانی تکرارشونده.", "cyclical-mood-symptoms", "premenstrual-dysphoric-disorder"),
    ("fc-stressor-linked", "در پریشانی مرتبط با عامل استرس‌زا چه رابطه‌ای باید بررسی شود؟", "رابطه زمانی میان عامل استرس‌زای قابل شناسایی، شروع ناراحتی و تغییر عملکرد.", "stressor-linked-distress", "adjustment-disorder"),
    ("fc-mistrust", "بی‌اعتمادی در یک تعریف آموزشی چیست؟", "انتظار یا تفسیر مکرر رفتار دیگران به‌عنوان غیرقابل اعتماد یا دارای نیت منفی، که باید با زمینه و شواهد بررسی شود.", "mistrust", "paranoid-personality-disorder"),
    ("fc-social-detachment", "فاصله‌گیری اجتماعی با اجتناب ناشی از ترس یکسان است؟", "نه. فاصله‌گیری می‌تواند با تمایل کم به نزدیکی همراه باشد، در حالی که اجتناب اجتماعی ممکن است با میل به رابطه و ترس از ارزیابی همزمان باشد.", "social-detachment", "schizoid-personality-disorder"),
    ("fc-unusual-beliefs", "در ارزیابی باورهای نامتعارف چه چیزی باید در نظر گرفته شود؟", "زمینه فرهنگی، میزان قطعیت و انعطاف‌پذیری باور، تجربه‌های ادراکی و اثر بر عملکرد.", "unusual-beliefs", "schizotypal-personality-disorder"),
    ("fc-attention-seeking", "چرا جلب توجه به‌تنهایی تشخیص نیست؟", "چون باید انگیزه، پایداری الگو، زمینه روابط و اثر عملکردی آن بررسی شود.", "attention-seeking", "histrionic-personality-disorder"),
    ("fc-grandiosity", "بزرگ‌منشی چیست؟", "ارزیابی اغراق‌شده از اهمیت، توانایی، جایگاه یا استحقاق خود که تفسیر آن به زمینه و پایداری الگو وابسته است.", "grandiosity", "narcissistic-personality-disorder"),
    ("fc-dependency", "وابستگی در چه زمانی می‌تواند مشکل‌ساز شود؟", "وقتی اتکای زیاد به دیگران برای تصمیم‌گیری و اطمینان، استقلال و عملکرد فرد را محدود کند.", "dependency", "dependent-personality-disorder"),
]


V4_FLASHCARDS = [
    ("fc-discount-positive", "بی‌اعتبار کردن نکات مثبت چه الگویی دارد؟", "شواهد مثبت پذیرفته نمی‌شود یا طوری کم‌ارزش می‌شود که ارزیابی منفی بدون اصلاح باقی بماند.", "discounting-the-positive", None),
    ("fc-emotional-reasoning", "«چون احساس می‌کنم بی‌کفایتم، پس واقعاً بی‌کفایتم» نمونه چیست؟", "استدلال هیجانی؛ احساس به‌عنوان مدرک مستقیم واقعیت استفاده شده است.", "emotional-reasoning", None),
    ("fc-labeling", "تفاوت برچسب‌زنی با توصیف رفتار چیست؟", "برچسب‌زنی یک خطا یا رفتار را به قضاوت هویتی کلی تبدیل می‌کند؛ توصیف رفتار روی همان رویداد مشخص می‌ماند.", "labeling", None),
    ("fc-magnification-minimization", "بزرگ‌نمایی و کوچک‌نمایی چه می‌کند؟", "وزن اطلاعات را نامتوازن می‌کند؛ جنبه منفی بزرگ‌تر و شواهد مثبت یا منابع مقابله کوچک‌تر دیده می‌شوند.", "magnification-minimization", None),
    ("fc-mental-filter", "فیلتر ذهنی چیست؟", "تمرکز انتخابی روی یک جزء منفی و نادیده گرفتن سایر اطلاعات مرتبط تجربه.", "mental-filter", None),
    ("fc-overgeneralization", "«یک بار بد پیش رفت، پس همیشه همین‌طور می‌شود» نمونه چیست؟", "تعمیم افراطی؛ از داده محدود یک قاعده کلی ساخته شده است.", "overgeneralization", None),
    ("fc-personalization", "شخصی‌سازی چیست؟", "نسبت دادن علت یا مسئولیت یک رویداد به خود بدون شواهد کافی درباره نقش واقعی فرد.", "personalization", None),
    ("fc-should-statements", "چه زمانی «باید» می‌تواند نشانه یک الگوی شناختی سخت باشد؟", "وقتی ترجیح یا ارزش به الزام مطلق و انعطاف‌ناپذیر تبدیل شود و خطا یا تفاوت غیرقابل قبول تلقی شود.", "should-must-statements", None),
    ("fc-tunnel-vision", "دید تونلی چیست؟", "دیدن عمدتاً جنبه‌های منفی فرد یا موقعیت و از دست دادن تصویر متوازن‌تر.", "tunnel-vision", None),
]


DISTORTION_PRACTICE_ITEMS = [
    ("dp-all-or-nothing-1", "«اگر این ارائه عالی نباشد یعنی کاملاً شکست خورده‌ام.» نزدیک‌ترین الگو کدام است؟", "all-or-nothing-thinking", ["catastrophizing", "labeling", "mental-filter"], "basic", "جمله نتیجه را فقط در دو قطب عالی یا شکست کامل می‌بیند و فضای میانی را حذف می‌کند."),
    ("dp-catastrophizing-1", "«اگر وسط ارائه مکث کنم، آبرویم برای همیشه از بین می‌رود.» نزدیک‌ترین الگو چیست؟", "catastrophizing", ["mind-reading", "personalization", "should-must-statements"], "basic", "پیامد یک مکث کوچک به نتیجه‌ای بسیار شدید و غیرقابل‌تحمل گسترش داده شده است."),
    ("dp-mind-reading-1", "«او جواب پیامم را دیر داد؛ حتماً فکر می‌کند آدم بی‌ارزشی هستم.» کدام الگو پررنگ‌تر است؟", "mind-reading", ["overgeneralization", "mental-filter", "labeling"], "basic", "درباره فکر طرف مقابل بدون شواهد کافی نتیجه قطعی گرفته شده است."),
    ("dp-discount-positive-1", "بعد از تحسین استاد می‌گوید: «این حساب نیست، فقط سؤال آسان بود.» کدام الگوست؟", "discounting-the-positive", ["mental-filter", "personalization", "emotional-reasoning"], "basic", "شاهد مثبت به‌جای وارد شدن در ارزیابی، بی‌اعتبار و کم‌ارزش شده است."),
    ("dp-emotional-reasoning-1", "«احساس می‌کنم مزاحم دیگرانم، پس واقعاً حضورم برایشان آزاردهنده است.» نزدیک‌ترین الگو چیست؟", "emotional-reasoning", ["mind-reading", "labeling", "catastrophizing"], "basic", "احساس شخصی به‌عنوان مدرک مستقیم برای واقعیت بیرونی استفاده شده است."),
    ("dp-labeling-1", "بعد از یک اشتباه می‌گوید: «من یک بازنده‌ام.» این جمله بیشتر به کدام الگو نزدیک است؟", "labeling", ["overgeneralization", "all-or-nothing-thinking", "personalization"], "basic", "یک رفتار یا خطا به یک برچسب کلی درباره هویت تبدیل شده است."),
    ("dp-magnification-1", "یک نقد کوچک را بسیار جدی می‌گیرد ولی چند بازخورد مثبت را تقریباً بی‌ارزش می‌داند. نزدیک‌ترین الگو چیست؟", "magnification-minimization", ["mental-filter", "discounting-the-positive", "catastrophizing"], "intermediate", "وزن شواهد نامتوازن شده است: بخش منفی بزرگ و بخش مثبت کوچک دیده می‌شود."),
    ("dp-mental-filter-1", "از ده بازخورد، نه مورد مثبت و یک مورد منفی است؛ فقط همان یک نقد را در ذهن نگه می‌دارد. کدام الگوست؟", "mental-filter", ["discounting-the-positive", "tunnel-vision", "overgeneralization"], "intermediate", "توجه به یک جزء منفی محدود شده و بقیه زمینه از ارزیابی کنار رفته است."),
    ("dp-overgeneralization-1", "«یک مصاحبه بد داشتم؛ من هیچ‌وقت در هیچ مصاحبه‌ای موفق نمی‌شوم.» کدام الگوست؟", "overgeneralization", ["all-or-nothing-thinking", "catastrophizing", "labeling"], "basic", "از یک تجربه محدود، نتیجه‌ای کلی و پایدار درباره همه موقعیت‌های آینده ساخته شده است."),
    ("dp-personalization-1", "دوستش امروز کم‌حرف است و بدون شواهد نتیجه می‌گیرد: «حتماً من کاری کرده‌ام که ناراحت شده.» کدام الگوست؟", "personalization", ["mind-reading", "emotional-reasoning", "mental-filter"], "intermediate", "علت وضعیت دیگری بدون شواهد کافی به خود فرد نسبت داده شده است."),
    ("dp-should-1", "«من باید همیشه بدون اشتباه باشم؛ خطا کردن غیرقابل قبول است.» نزدیک‌ترین الگو چیست؟", "should-must-statements", ["all-or-nothing-thinking", "labeling", "catastrophizing"], "basic", "یک ترجیح یا استاندارد به الزام مطلق و انعطاف‌ناپذیر تبدیل شده است."),
    ("dp-tunnel-vision-1", "در ارزیابی یک همکار فقط ضعف‌های او را می‌بیند و تقریباً هیچ رفتار مفید یا خنثی را وارد قضاوت نمی‌کند. کدام الگوست؟", "tunnel-vision", ["mental-filter", "labeling", "personalization"], "intermediate", "کل تصویر از زاویه‌ای عمدتاً منفی و محدود دیده می‌شود."),
    ("dp-filter-vs-discount", "فرد تعریف همکار را شنیده اما می‌گوید: «تعریفش ارزشی ندارد چون فقط مودب بود.» کدام گزینه دقیق‌تر است؟", "discounting-the-positive", ["mental-filter", "tunnel-vision", "overgeneralization"], "advanced", "اینجا داده مثبت دیده شده اما اعتبار آن فعالانه رد شده است؛ این با صرفاً ندیدن یا تمرکز نکردن بر داده مثبت فرق دارد."),
    ("dp-label-vs-overgeneralize", "«در این آزمون خراب کردم، پس من آدم احمقی هستم.» کدام الگو مستقیم‌تر است؟", "labeling", ["overgeneralization", "all-or-nothing-thinking", "emotional-reasoning"], "advanced", "نتیجه از عملکرد مشخص به یک برچسب هویتی کلی تبدیل شده است؛ تعمیم افراطی بیشتر قاعده را به موقعیت‌های متعدد گسترش می‌دهد."),
    ("dp-mind-vs-personalize", "«او ساکت است؛ حتماً از من بدش می‌آید.» کدام الگو مستقیم‌تر است؟", "mind-reading", ["personalization", "emotional-reasoning", "catastrophizing"], "advanced", "هسته جمله ادعای قطعی درباره حالت ذهنی دیگری است؛ شخصی‌سازی بیشتر روی نسبت دادن علت رویداد به خود متمرکز است."),
    ("dp-catastrophe-vs-magnify", "«اگر این درس را بیفتم، آینده‌ام کاملاً نابود می‌شود و دیگر هیچ راهی ندارم.» کدام الگو مستقیم‌تر است؟", "catastrophizing", ["magnification-minimization", "all-or-nothing-thinking", "should-must-statements"], "advanced", "پیامد منفی به بدترین نتیجه بسیار شدید و بدون راه مقابله تبدیل شده است."),
    ("dp-emotion-vs-mind", "«وقتی کنار آن‌ها هستم احساس می‌کنم طرد شده‌ام، پس حتماً واقعاً من را طرد کرده‌اند.» کدام الگو مستقیم‌تر است؟", "emotional-reasoning", ["mind-reading", "personalization", "overgeneralization"], "advanced", "استدلال اصلی از احساس به واقعیت حرکت می‌کند؛ ممکن است مؤلفه بین‌فردی هم باشد اما شکل استنتاج هیجانی برجسته‌تر است."),
    ("dp-all-vs-should", "«اگر بهترین نباشم، یعنی هیچ ارزشی ندارم.» کدام الگو مستقیم‌تر است؟", "all-or-nothing-thinking", ["should-must-statements", "labeling", "discounting-the-positive"], "advanced", "ارزش فرد به دو حالت بهترین بودن یا بی‌ارزش بودن تقسیم شده است؛ ساختار دو قطبی جمله عنصر اصلی است."),
]


CHALLENGES = [
    ("فرد می‌گوید: «اگر نمره‌ام عالی نشود، یعنی کاملاً شکست خورده‌ام.» نزدیک‌ترین مفهوم چیست؟", ["تفکر همه یا هیچ", "ذهن‌خوانی", "گسستگی", "برانگیختگی بالا"], 0, "این جمله یک طیف را به دو قطب موفقیت کامل یا شکست کامل تبدیل می‌کند.", "all-or-nothing-thinking", None),
    ("کدام مفهوم بیشتر آینده‌محور و درباره پیامدهای احتمالی است؟", ["نگرانی", "نشخوار فکری", "فقدان لذت", "مانیا"], 0, "نگرانی معمولاً آینده‌محورتر از نشخوار فکری است.", "worry", "generalized-anxiety-disorder"),
    ("رفتاری که برای جلوگیری از خجالت در جمع به آن تکیه می‌کنیم و ممکن است باور ترسناک را آزمایش‌نشده نگه دارد چیست؟", ["رفتار ایمنی", "فعال‌سازی رفتاری", "گسستگی", "باور هسته‌ای"], 0, "رفتارهای ایمنی می‌توانند تجربه کامل موقعیت و آزمون پیش‌بینی را محدود کنند.", "safety-behaviors", "social-anxiety-disorder"),
    ("«دوستم جواب نداده، پس حتماً از من بدش می‌آید» نزدیک‌ترین تحریف کدام است؟", ["ذهن‌خوانی", "فاجعه‌سازی", "همه یا هیچ", "اجتناب"], 0, "در ذهن‌خوانی درباره فکر دیگران بدون شواهد کافی نتیجه قطعی گرفته می‌شود.", "mind-reading", None),
    ("کدام مفهوم یکی از نشانه‌های مهم در الگوهای افسردگی است؟", ["فقدان لذت", "کاهش نیاز به خواب در مانیا", "اعمال اجباری", "حمله پانیک"], 0, "کاهش علاقه یا توان لذت یکی از مفاهیم مهم در ارزیابی افسردگی است.", "anhedonia", "major-depressive-disorder"),
    ("کدام گزینه در یک چرخه وسواسی می‌تواند پس از فکر مزاحم برای کاهش موقت اضطراب رخ دهد؟", ["عمل اجباری", "مانیا", "فعال‌سازی رفتاری", "ذهن‌خوانی"], 0, "اعمال اجباری در برخی چرخه‌های OCD برای کاهش پریشانی انجام می‌شوند.", "compulsions", "obsessive-compulsive-disorder"),
    ("در یک برنامه مواجهه، هدف اصلی کدام است؟", ["حرکت برنامه‌ریزی‌شده به سمت موقعیت ترسناک و یادگیری جدید", "حذف کامل هر اضطراب قبل از شروع", "تکیه بیشتر بر رفتارهای ایمنی", "اجتناب از همه محرک‌ها"], 0, "مواجهه فرصت یادگیری جدید را در تماس با تجربه ترسناک فراهم می‌کند.", "exposure", None),
    ("کدام مفهوم با کاهش محسوس علاقه یا لذت تعریف می‌شود؟", ["Anhedonia", "Impulsivity", "Dissociation", "Worry"], 0, "Anhedonia به کاهش علاقه یا توان تجربه لذت اشاره دارد.", "anhedonia", None),
    ("فرد ساعت‌ها اشتباه مکالمه دیروز را بدون رسیدن به اقدام مؤثر مرور می‌کند. نزدیک‌ترین مفهوم چیست؟", ["نشخوار فکری", "نگرانی", "مواجهه", "هیپومانیا"], 0, "نشخوار فکری معمولاً به مرور تکراری ناراحتی، علت‌ها یا پیامدهای آن اشاره دارد.", "rumination", None),
    ("برای افتراق Bipolar I و II کدام مفهوم کلیدی‌تر است؟", ["مانیا کامل", "فوبیای خاص", "عمل اجباری", "ذهن‌خوانی"], 0, "وجود سابقه مانیا کامل برای Bipolar I اهمیت مرکزی دارد.", "mania", "bipolar-i-disorder"),
    ("پس از تروما، واکنش شدید از جا پریدن و گوش‌به‌زنگی بیشتر با کدام مفهوم مرتبط است؟", ["برانگیختگی بالا", "فقدان لذت", "کمال‌گرایی", "افکار خودکار"], 0, "این الگو با hyperarousal سازگارتر است.", "hyperarousal", "post-traumatic-stress-disorder"),
    ("کدام جمله درباره فکر مزاحم دقیق‌تر است؟", ["وجود آن به‌تنهایی اختلال را ثابت نمی‌کند", "همیشه نشانه روان‌پریشی است", "همیشه باید با عمل اجباری همراه باشد", "فقط در OCD دیده می‌شود"], 0, "فکر مزاحم می‌تواند در افراد مختلف رخ دهد؛ الگوی پاسخ و اثر عملکردی برای ارزیابی مهم‌اند.", "intrusive-thoughts", None),
]


def seed_v3_content(disorder_objs, source_objs):
    concept_objs = {}
    distortion_slugs = set(DISTORTION_DETAILS)
    all_concepts = CONCEPTS + V4_CONCEPTS

    for slug, en, fa, kind, simple, academic, example in all_concepts:
        enrichment = CONCEPT_ENRICHMENT.get(slug, {})
        if slug in distortion_slugs:
            enrichment = {**enrichment, "domain": "cbt", "subtype": "cognitive_distortion"}
        details = DISTORTION_DETAILS.get(slug, {})
        concept, _ = Concept.objects.update_or_create(
            slug=slug,
            defaults={
                "name_en": en,
                "name_fa": fa,
                "kind": kind,
                "domain": enrichment.get("domain", "general"),
                "subtype": enrichment.get("subtype", "general"),
                "simple_definition": simple,
                "academic_definition": academic,
                "example": example,
                "counterexample": details.get("counterexample", ""),
                "recognition_cues": details.get("recognition_cues", ""),
                "common_confusions": details.get("common_confusions", ""),
                "is_active": True,
            },
        )
        concept_objs[slug] = concept

    beck_source, _ = SourceReference.objects.update_or_create(
        title="Testing Your Thoughts Worksheet",
        organization="Beck Institute for Cognitive Behavior Therapy",
        defaults={
            "citation": "Beck Institute. Testing Your Thoughts worksheet; adapted from J. Beck, Cognitive Behavior Therapy: Basics and Beyond, 3rd edition.",
            "url": "https://beckinstitute.org/wp-content/uploads/2021/08/Testing-Your-Thoughts-Worksheet.pdf",
            "source_type": "educational_cbt",
        },
    )

    for concept_slug, text, language, alias_type in CONCEPT_ALIASES:
        ConceptAlias.objects.update_or_create(
            concept=concept_objs[concept_slug],
            text=text,
            language=language,
            defaults={"alias_type": alias_type},
        )

    for source_slug, target_slug, relation_type, explanation in CONCEPT_RELATIONS:
        ConceptRelationship.objects.update_or_create(
            source_concept=concept_objs[source_slug],
            target_concept=concept_objs[target_slug],
            relationship_type=relation_type,
            defaults={"explanation": explanation},
        )

    distortion_root = concept_objs["cognitive-distortions"]
    for distortion_slug in sorted(distortion_slugs):
        if distortion_slug == "cognitive-distortions":
            continue
        if distortion_slug not in {"all-or-nothing-thinking", "catastrophizing", "mind-reading"}:
            relation, _ = ConceptRelationship.objects.update_or_create(
                source_concept=concept_objs[distortion_slug],
                target_concept=distortion_root,
                relationship_type="part_of",
                defaults={"explanation": "این الگو در فهرست آموزشی تحریف‌های شناختی Beck Institute آمده است."},
            )
        else:
            relation = ConceptRelationship.objects.get(
                source_concept=concept_objs[distortion_slug],
                target_concept=distortion_root,
                relationship_type="part_of",
            )
        ConceptRelationshipSource.objects.get_or_create(relationship=relation, source=beck_source)

    for order, (disorder_slug, concept_slug, role) in enumerate(DISORDER_CONCEPTS):
        DisorderConcept.objects.update_or_create(
            disorder=disorder_objs[disorder_slug],
            concept=concept_objs[concept_slug],
            role=role,
            defaults={"sort_order": order},
        )

    symptom_objs = {
        symptom.slug: symptom
        for symptom in Symptom.objects.filter(slug__in=[row[1] for row in CONCEPT_SYMPTOMS])
    }
    for order, (concept_slug, symptom_slug, relationship_type) in enumerate(CONCEPT_SYMPTOMS):
        symptom = symptom_objs.get(symptom_slug)
        if not symptom:
            continue
        ConceptSymptom.objects.update_or_create(
            concept=concept_objs[concept_slug],
            symptom=symptom,
            relationship_type=relationship_type,
            defaults={
                "sort_order": order,
                "explanation": "این Concept و Symptom به یک سازه آموزشی نام‌گذاری‌شده اشاره می‌کنند؛ این لینک برای اتصال لایه‌های اطلس ثبت شده است.",
            },
        )

    for concept in concept_objs.values():
        if concept.slug in distortion_slugs or concept.slug == "cognitive-distortions":
            ConceptSource.objects.get_or_create(concept=concept, source=beck_source)
            ConceptSource.objects.filter(concept=concept).exclude(source=beck_source).delete()
        else:
            for source in source_objs:
                ConceptSource.objects.get_or_create(concept=concept, source=source)

    all_flashcards = FLASHCARDS + V4_FLASHCARDS
    for order, (slug, front, back, concept_slug, disorder_slug) in enumerate(all_flashcards):
        Flashcard.objects.update_or_create(
            slug=slug,
            defaults={
                "front": front,
                "back": back,
                "concept": concept_objs.get(concept_slug) if concept_slug else None,
                "disorder": disorder_objs.get(disorder_slug) if disorder_slug else None,
                "difficulty": "basic" if order < 18 else "intermediate",
                "sort_order": order,
                "is_active": True,
                "seed_managed": True,
            },
        )
    Flashcard.objects.filter(seed_managed=True).exclude(
        slug__in=[row[0] for row in all_flashcards]
    ).update(is_active=False)

    for order, (slug, prompt, target_slug, distractor_slugs, difficulty, explanation) in enumerate(DISTORTION_PRACTICE_ITEMS):
        item, _ = CognitiveDistortionPracticeItem.objects.update_or_create(
            slug=slug,
            defaults={
                "prompt": prompt,
                "explanation": explanation,
                "difficulty": difficulty,
                "target_concept": concept_objs[target_slug],
                "sort_order": order,
                "is_active": True,
                "seed_managed": True,
            },
        )
        choice_slugs = [target_slug, *distractor_slugs]
        shift = order % len(choice_slugs)
        choice_slugs = choice_slugs[shift:] + choice_slugs[:shift]
        keep_concept_ids = []
        for choice_order, choice_slug in enumerate(choice_slugs):
            choice_concept = concept_objs[choice_slug]
            keep_concept_ids.append(choice_concept.id)
            CognitiveDistortionPracticeChoice.objects.update_or_create(
                item=item,
                concept=choice_concept,
                defaults={
                    "text": choice_concept.name_fa or choice_concept.name_en,
                    "is_correct": choice_slug == target_slug,
                    "sort_order": choice_order,
                    "is_active": True,
                },
            )
        item.choices.exclude(concept_id__in=keep_concept_ids).update(is_active=False, is_correct=False)
    CognitiveDistortionPracticeItem.objects.filter(seed_managed=True).exclude(
        slug__in=[row[0] for row in DISTORTION_PRACTICE_ITEMS]
    ).update(is_active=False)

    for order, (prompt, choices, correct_index, explanation, concept_slug, disorder_slug) in enumerate(CHALLENGES):
        challenge = DailyChallenge.objects.filter(sort_order=order).order_by("id").first()
        defaults = {
            "prompt": prompt,
            "explanation": explanation,
            "concept": concept_objs.get(concept_slug) if concept_slug else None,
            "disorder": disorder_objs.get(disorder_slug) if disorder_slug else None,
            "sort_order": order,
            "is_active": True,
            "seed_managed": True,
        }
        if challenge:
            for key, value in defaults.items():
                setattr(challenge, key, value)
            challenge.save()
        else:
            challenge = DailyChallenge.objects.create(**defaults)
        active_choice_orders = []
        for choice_order, text in enumerate(choices):
            active_choice_orders.append(choice_order)
            choice = DailyChallengeChoice.objects.filter(challenge=challenge, sort_order=choice_order).order_by("id").first()
            values = {
                "text": text,
                "is_correct": choice_order == correct_index,
                "sort_order": choice_order,
                "is_active": True,
            }
            if choice:
                choice.text = values["text"]
                choice.is_correct = values["is_correct"]
                choice.is_active = True
                choice.save(update_fields=("text", "is_correct", "sort_order", "is_active"))
            else:
                DailyChallengeChoice.objects.create(challenge=challenge, **values)
        challenge.choices.exclude(sort_order__in=active_choice_orders).update(is_active=False, is_correct=False)
    DailyChallenge.objects.filter(seed_managed=True, sort_order__gte=len(CHALLENGES)).update(is_active=False)

    return {
        "concepts": len(all_concepts),
        "cognitive_distortions": len(distortion_slugs),
        "concept_aliases": len(CONCEPT_ALIASES),
        "concept_symptom_links": len(CONCEPT_SYMPTOMS),
        "flashcards": len(all_flashcards),
        "distortion_practice_items": len(DISTORTION_PRACTICE_ITEMS),
        "daily_challenges": len(CHALLENGES),
    }
