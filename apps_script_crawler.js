/**
 * 법조 아침보고용 구글 앱스 스크립트 (GAS) 통합 크롤러 (No-Library 버전)
 * 
 * [특징]
 * - 외부 라이브러리(Cheerio 등) 추가 없이 순수 자바스크립트(정규식)만으로 작동합니다.
 * - 라이브러리 추가 오류 걱정 없이 복사 붙여넣기만 하면 즉시 실행할 수 있습니다.
 * 
 * [설정 방법]
 * 1. 구글 시트의 [확장 프로그램] ➔ [Apps Script]를 클릭하여 편집기를 엽니다.
 * 2. 편집기의 기존 코드 전체를 지우고, 본 스크립트로 덮어씁니다.
 * 3. 시트 Config 탭의 C1셀에 'naver_client_id', C2셀에 발급받은 네이버 Client ID를 넣고,
 *    D1셀에 'naver_client_secret', D2셀에 Secret 값을 입력해 둡니다.
 * 4. 매일 오전 05:30에 'runCrawl' 함수가 실행되도록 [트리거(시계 아이콘)]를 등록합니다.
 */

// 매체 정보 및 RSS 피드 목록 정의
const NEWSPAPERS = {
  "경향신문": "032",
  "국민일보": "005",
  "동아일보": "020",
  "문화일보": "021",
  "서울신문": "081",
  "세계일보": "022",
  "중앙일보": "025",
  "한겨레": "028",
  "한국일보": "469"
};

const RSS_FEEDS = [
  {"source": "뉴시스", "section": "정치", "url": "https://nwww.newsis.com/RSS/politics.xml"},
  {"source": "뉴시스", "section": "사회", "url": "https://nwww.newsis.com/RSS/society.xml"},
  {"source": "연합뉴스", "section": "정치", "url": "https://www.yna.co.kr/rss/politics.xml"},
  {"source": "연합뉴스", "section": "사회", "url": "https://www.yna.co.kr/rss/society.xml"},
  {"source": "경향신문", "section": "정치", "url": "https://www.khan.co.kr/rss/rssdata/politic_news.xml"},
  {"source": "경향신문", "section": "사회", "url": "https://www.khan.co.kr/rss/rssdata/society_news.xml"},
  {"source": "한겨레", "section": "정치", "url": "http://www.hani.co.kr/rss/politics/"},
  {"source": "한겨레", "section": "사회", "url": "http://www.hani.co.kr/rss/society/"},
  {"source": "동아일보", "section": "정치", "url": "http://rss.donga.com/politics.xml"},
  {"source": "동아일보", "section": "사회", "url": "http://rss.donga.com/national.xml"},
  {"source": "SBS", "section": "정치", "url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01&plink=RSSREADER"},
  {"source": "SBS", "section": "사회", "url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=03&plink=RSSREADER"},
  {"source": "JTBC", "section": "정치", "url": "https://fs.jtbc.co.kr/RSS/politics.xml"},
  {"source": "JTBC", "section": "사회", "url": "https://fs.jtbc.co.kr/RSS/society.xml"},
  {"source": "TV조선", "section": "정치", "url": "https://news.tvchosun.com/site/data/rss/politics.xml"},
  {"source": "TV조선", "section": "사회", "url": "https://news.tvchosun.com/site/data/rss/national.xml"},
  {"source": "노컷뉴스", "section": "사회", "url": "https://rss.nocutnews.co.kr/category/society.xml"},
  {"source": "로리더", "section": "법률", "url": "https://www.lawleader.co.kr/rss"},
  {"source": "법률저널", "section": "법률", "url": "http://www.lec.co.kr/rss/allArticle.xml"}
];

const BROADCAST_SOURCES = ["KBS", "SBS", "MBC", "JTBC", "채널A", "TV조선"];

// 메인 크롤링 실행 함수
function runCrawl(params) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet();
  const config = loadConfig(sheet);
  
  // 팝업 대화상자에서 매개변수가 전달된 경우 임시 오버라이드
  if (params) {
    if (params.startDate !== undefined) config.startDate = params.startDate.replace(/[^0-9]/g, "");
    if (params.endDate !== undefined) config.endDate = params.endDate.replace(/[^0-9]/g, "");
    if (params.startTime !== undefined) config.startTime = params.startTime;
    if (params.endTime !== undefined) config.endTime = params.endTime;
    if (params.morningReportMode !== undefined) config.morningReportMode = params.morningReportMode;
  } else {
    // [안전장치] 일일 자동 예약 트리거(params가 없음)로 실행될 경우
    // 현재 실행 시점을 기준으로 최근 12시간 범위 of 뉴스만 동적으로 지정하여 수집 및 필터링합니다.
    const now = new Date();
    const past = new Date(now.getTime() - 12 * 60 * 60 * 1000);
    
    const formatYMD = function(d) {
      const y = d.getFullYear();
      const m = ('0' + (d.getMonth() + 1)).slice(-2);
      const date = ('0' + d.getDate()).slice(-2);
      return y + m + date;
    };
    
    const formatHM = function(d) {
      const h = ('0' + d.getHours()).slice(-2);
      const min = ('0' + d.getMinutes()).slice(-2);
      return h + ":" + min;
    };
    
    config.startDate = formatYMD(past);
    config.endDate = formatYMD(now);
    config.startTime = formatHM(past);
    config.endTime = formatHM(now);
  }
  
  const dates = getDatesInRange(config.startDate, config.endDate);
  const datesSet = new Set(dates);
  Logger.log("크롤링 대상 날짜 목록: " + JSON.stringify(dates));
  
  // 1. Raw_Articles 시트에서 해당 날짜 범위에 포함되는 기존 기사 목록을 먼저 로드합니다.
  let collectedArticles = loadExistingArticlesFromRaw(sheet, datesSet);
  Logger.log("기존 Raw_Articles에서 로드 완료: " + collectedArticles.length + "건.");
  
  const existingUrls = new Set(collectedArticles.map(art => art.url));
  let newArticles = [];
  
  for (let dateStr of dates) {
    Logger.log("--- 크롤링 시작 날짜: " + dateStr + " ---");
    
    // 1. 네이버 지면 기사 크롤링
    for (let newspaper in NEWSPAPERS) {
      try {
        const paperArticles = crawlPaperNewspaper(newspaper, NEWSPAPERS[newspaper], dateStr);
        newArticles = newArticles.concat(paperArticles);
      } catch(e) {
        Logger.log("지면 크롤링 실패 (" + newspaper + "): " + e);
      }
    }
    
    // 2. RSS 피드 온라인 수집
    for (let feed of RSS_FEEDS) {
      try {
        const rssArticles = crawlRssFeed(feed, dateStr);
        newArticles = newArticles.concat(rssArticles);
      } catch(e) {
        Logger.log("RSS 수집 실패 (" + feed.source + " " + feed.section + "): " + e);
      }
    }
    
    // 3. 네이버 OpenAPI 검색어 수집 (Fallback)
    if (config.naverClientId && config.naverClientSecret) {
      for (let kw of config.bodyKeywords) {
        if (kw.length < 2) continue;
        try {
          const apiArticles = crawlNaverNewsApi(kw, config.naverClientId, config.naverClientSecret, dateStr, config.excludeKeywords);
          newArticles = newArticles.concat(apiArticles);
        } catch(e) {
          Logger.log("네이버 API 검색 수집 실패 (" + kw + "): " + e);
        }
      }
    }
  }
  
  Logger.log("신규 수집 완료: " + newArticles.length + "건. 기존 수집본과 병합을 시도합니다.");
  collectedArticles = collectedArticles.concat(newArticles);
  Logger.log("총 병합 수집 대상 기사: " + collectedArticles.length + "건.");

  // 날짜/시간 범위 필터 생성
  const startLimit = getLimitDate(config.startDate, config.startTime, false);
  const endLimit = getLimitDate(config.endDate, config.endTime, true);

  // 4. 키워드 필터링, 시간대 필터링 및 1차 제외 처리
  let filtered = filterArticles(collectedArticles, config.bodyKeywords, config.excludeKeywords, existingUrls, config.naverClientId, config.naverClientSecret, startLimit, endLimit);
  Logger.log("키워드/시간 필터링 통과: " + filtered.length + "건.");

  // 5. 중복 기사 제거 및 우선순위 선정 (Deduplication)
  let deduplicated = deduplicateArticles(filtered);
  Logger.log("중복 제거 후 최종 기사: " + deduplicated.length + "건.");

  // 6. 구글 시트에 데이터 쓰기
  writeToSpreadsheet(sheet, deduplicated, config);
  Logger.log("--- 크롤링 및 시트 적재 완료 ---");
  
  // 텔레그램 알림 전송 (크롤링 완료 알림)
  if (config.telegramBotToken && config.telegramChatId) {
    try {
      const sheetUrl = sheet.getUrl();
      sendTelegramNotification(config.telegramBotToken, config.telegramChatId, sheetUrl);
      Logger.log("텔레그램 알림 전송 완료");
    } catch(e) {
      Logger.log("텔레그램 알림 전송 실패: " + e);
    }
  }
}

// 오늘 날짜 구하기 (YYYYMMDD)
function getTodayString() {
  const d = new Date();
  const y = d.getFullYear();
  const m = ('0' + (d.getMonth() + 1)).slice(-2);
  const date = ('0' + d.getDate()).slice(-2);
  return y + m + date;
}

// 시작일과 종료일 범위 날짜 생성 함수 (YYYYMMDD)
function getDatesInRange(startStr, endStr) {
  const dates = [];
  const today = getTodayString();
  
  const start = startStr ? startStr.replace(/[^0-9]/g, "") : "";
  const end = endStr ? endStr.replace(/[^0-9]/g, "") : "";
  
  if (!start) {
    dates.push(today);
    return dates;
  }
  
  const targetEnd = end || start;
  
  const startYear = parseInt(start.substring(0, 4), 10);
  const startMonth = parseInt(start.substring(4, 6), 10) - 1;
  const startDay = parseInt(start.substring(6, 8), 10);
  
  const endYear = parseInt(targetEnd.substring(0, 4), 10);
  const endMonth = parseInt(targetEnd.substring(4, 6), 10) - 1;
  const endDay = parseInt(targetEnd.substring(6, 8), 10);
  
  let currentDate = new Date(startYear, startMonth, startDay);
  const lastDate = new Date(endYear, endMonth, endDay);
  
  // 비정상적인 날짜 입력 방지 및 최대 30일 제한
  if (isNaN(currentDate.getTime()) || isNaN(lastDate.getTime()) || currentDate > lastDate) {
    dates.push(today);
    return dates;
  }
  
  let count = 0;
  while (currentDate <= lastDate && count < 30) {
    const y = currentDate.getFullYear();
    const m = ('0' + (currentDate.getMonth() + 1)).slice(-2);
    const d = ('0' + currentDate.getDate()).slice(-2);
    dates.push(y + m + d);
    currentDate.setDate(currentDate.getDate() + 1);
    count++;
  }
  
  return dates;
}

// Config 시트에서 키워드 및 API 인증 키 로드
function loadConfig(sheet) {
  const ws = sheet.getSheetByName("Config");
  if (!ws) {
    return { 
      bodyKeywords: [], excludeKeywords: [], 
      naverClientId: "", naverClientSecret: "", 
      n8nWebhookUrl: "", telegramBotToken: "", telegramChatId: "", 
      startDate: "", endDate: "", 
      startTime: "", endTime: "", 
      morningReportMode: "유지" 
    };
  }
  
  const lastRow = ws.getLastRow();
  if (lastRow <= 1) {
    return { 
      bodyKeywords: [], excludeKeywords: [], 
      naverClientId: "", naverClientSecret: "", 
      n8nWebhookUrl: "", telegramBotToken: "", telegramChatId: "", 
      startDate: "", endDate: "", 
      startTime: "", endTime: "", 
      morningReportMode: "유지" 
    };
  }
  
  // 12열(L열)까지 읽습니다.
  const allValues = ws.getRange(1, 1, lastRow, 12).getValues();
  const bodyKeywords = [];
  const excludeKeywords = [];
  
  for (let i = 1; i < allValues.length; i++) {
    const bVal = allValues[i][0] ? String(allValues[i][0]).trim() : "";
    const eVal = allValues[i][1] ? String(allValues[i][1]).trim() : "";
    if (bVal) bodyKeywords.push(bVal);
    if (eVal) excludeKeywords.push(eVal);
  }
  
  const naverClientId = allValues[1][2] ? String(allValues[1][2]).trim() : "";
  const naverClientSecret = allValues[1][3] ? String(allValues[1][3]).trim() : "";
  const n8nWebhookUrl = allValues[1][4] ? String(allValues[1][4]).trim() : "";
  const telegramBotToken = allValues[1][5] ? String(allValues[1][5]).trim() : "";
  const telegramChatId = allValues[1][6] ? String(allValues[1][6]).trim() : "";
  const startDate = allValues[1][7] ? String(allValues[1][7]).trim() : "";
  const endDate = allValues[1][8] ? String(allValues[1][8]).trim() : "";
  const startTime = allValues[1][9] ? String(allValues[1][9]).trim() : "";
  const endTime = allValues[1][10] ? String(allValues[1][10]).trim() : "";
  const morningReportMode = allValues[1][11] ? String(allValues[1][11]).trim() : "과거 기사 유지";
  
  return {
    bodyKeywords: bodyKeywords,
    excludeKeywords: excludeKeywords,
    naverClientId: naverClientId,
    naverClientSecret: naverClientSecret,
    n8nWebhookUrl: n8nWebhookUrl,
    telegramBotToken: telegramBotToken,
    telegramChatId: telegramChatId,
    startDate: startDate,
    endDate: endDate,
    startTime: startTime,
    endTime: endTime,
    morningReportMode: morningReportMode
  };
}

/**
 * Raw_Articles 시트에서 이미 크롤링된 기사의 URL 목록을 Set으로 가져옵니다.
 */
function getExistingUrls(sheet) {
  const ws = sheet.getSheetByName("Raw_Articles");
  if (!ws) return new Set();
  
  const lastRow = ws.getLastRow();
  if (lastRow <= 1) return new Set();
  
  const lastCol = ws.getLastColumn();
  const headers = ws.getRange(1, 1, 1, lastCol).getValues()[0].map(h => String(h).trim());
  
  let urlColIdx = -1;
  const urlNames = ["URL", "url", "link"];
  for (let name of urlNames) {
    const idx = headers.indexOf(name);
    if (idx !== -1) {
      urlColIdx = idx + 1; // 1-based index for getRange
      break;
    }
  }
  
  // 매칭되는 열을 찾지 못했다면 기존 백업인 7번째 열(G열) 적용
  if (urlColIdx === -1) urlColIdx = 7;
  
  const urls = ws.getRange(2, urlColIdx, lastRow - 1, 1).getValues();
  const urlSet = new Set();
  for (let i = 0; i < urls.length; i++) {
    const url = urls[i][0] ? String(urls[i][0]).trim() : "";
    if (url) urlSet.add(url);
  }
  return urlSet;
}

// 네이버 지면 기사 스크래퍼 (순수 JS 문자열 및 RegExp 파싱)
function crawlPaperNewspaper(newspaper, oid, dateStr) {
  const articles = [];
  const url = "https://news.naver.com/main/list.naver?mode=LPOD&mid=sec&oid=" + oid + "&listType=paper&date=" + dateStr;
  
  const options = {
    "muteHttpExceptions": true,
    "headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
  };
  
  const response = UrlFetchApp.fetch(url, options);
  if (response.getResponseCode() !== 200) return articles;
  
  const html = response.getContentText("euc-kr");
  
  // 섹션 분할 정규식
  const sectionRegex = /<h4[^>]*class=["']paper_h4["'][^>]*>([\s\S]*?)<\/h4>([\s\S]*?)(?=<h4|$)/g;
  let match;
  
  while ((match = sectionRegex.exec(html)) !== null) {
    const sectionName = cleanHtmlText(match[1]);
    const sectionHtml = match[2];
    
    // 리스트 내 개별 기사 파싱
    const liRegex = /<li>([\s\S]*?)<\/li>/g;
    let liMatch;
    
    while ((liMatch = liRegex.exec(sectionHtml)) !== null) {
      const liHtml = liMatch[1];
      const aRegex = /<a[^>]*href=["']([^"']*\/mnews\/article\/[^"']*)["'][^>]*>([\s\S]*?)<\/a>/;
      const aMatch = aRegex.exec(liHtml);
      if (!aMatch) continue;
      
      let articleUrl = aMatch[1];
      if (articleUrl.startsWith("/")) {
        articleUrl = "https://news.naver.com" + articleUrl;
      }
      
      const title = cleanHtmlText(aMatch[2]);
      
      // lede 요약본
      const ledeRegex = /<span[^>]*class=["']lede["'][^>]*>([\s\S]*?)<\/span>/;
      const ledeMatch = ledeRegex.exec(liHtml);
      const lede = ledeMatch ? cleanHtmlText(ledeMatch[1]) : "";
      
      if (title && articleUrl) {
        articles.push({
          "date": dateStr,
          "published_at": "",
          "source": newspaper,
          "article_type": "지면",
          "paper_section": sectionName,
          "title": title,
          "url": articleUrl,
          "summary": lede,
          "body": "",
          "crawl_source": oid,
          "selected_for_report": "FALSE"
        });
      }
    }
  }
  
  return articles;
}

// RSS 수집기 (RegExp 기반으로 유연하게 XML 파싱)
function crawlRssFeed(feed, todayStr) {
  const articles = [];
  const options = { 
    "muteHttpExceptions": true, 
    "timeout": 8000,
    "headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
  };
  
  let response;
  try {
    response = UrlFetchApp.fetch(feed.url, options);
  } catch(e) {
    Logger.log("RSS Fetch 실패 (" + feed.source + "): " + e);
    return articles;
  }
  
  if (response.getResponseCode() !== 200) return articles;
  
  const xml = response.getContentText();
  
  // 엄격한 XmlService 대신 정규식으로 <item> 또는 <entry> 태그 파싱
  const itemRegex = /<(item|entry)>([\s\S]*?)<\/\1>/gi;
  let match;
  let rawItems = [];
  
  while ((match = itemRegex.exec(xml)) !== null) {
    const itemHtml = match[2];
    
    // 제목 추출
    const titleMatch = /<title>([\s\S]*?)<\/title>/i.exec(itemHtml);
    let title = titleMatch ? titleMatch[1] : "";
    title = title.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1"); // CDATA 스트립
    
    // 링크 추출
    let link = "";
    const linkMatch = /<link>([\s\S]*?)<\/link>/i.exec(itemHtml);
    if (linkMatch) {
      link = linkMatch[1];
    } else {
      const linkHrefMatch = /<link[^>]*href=["']([^"']*)["']/i.exec(itemHtml);
      link = linkHrefMatch ? linkHrefMatch[1] : "";
    }
    link = link.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1");
    
    // 요약문 추출
    const descMatch = /<(description|summary)>([\s\S]*?)<\/\1>/i.exec(itemHtml);
    let description = descMatch ? descMatch[2] : "";
    description = description.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1");
    
    rawItems.push({
      title: title.trim(),
      link: link.trim(),
      description: description.trim()
    });
  }
  
  const maxItems = Math.min(rawItems.length, 30);
  for (let i = 0; i < maxItems; i++) {
    const item = rawItems[i];
    let title = cleanHtmlText(item.title);
    let link = item.link;
    let description = cleanHtmlText(item.description);
    
    if (!title || !link) continue;
    
    const isExclusive = title.indexOf("단독") !== -1;
    const isWire = feed.source === "연합뉴스" || feed.source === "뉴시스";
    
    // 통신사(연합뉴스/뉴시스)가 아니면 오직 "단독" 기사만 수집
    if (!isWire && !isExclusive) continue;
    
    articles.push({
      "date": todayStr,
      "published_at": Utilities.formatDate(new Date(), "GMT+09:00", "yyyy-MM-dd HH:mm:ss"),
      "source": feed.source,
      "article_type": isWire ? "통신" : "온라인",
      "paper_section": feed.section,
      "title": title,
      "url": link,
      "summary": description,
      "body": "",
      "crawl_source": "rss",
      "selected_for_report": "FALSE"
    });
  }
  
  return articles;
}

// 네이버 OpenAPI 뉴스 검색
function crawlNaverNewsApi(keyword, clientId, clientSecret, todayStr, excludeKeywords) {
  const articles = [];
  const url = "https://openapi.naver.com/v1/search/news.json?query=" + encodeURIComponent(keyword) + "&display=50&sort=date";
  
  const options = {
    "headers": {
      "X-Naver-Client-Id": clientId,
      "X-Naver-Client-Secret": clientSecret
    },
    "muteHttpExceptions": true
  };
  
  const response = UrlFetchApp.fetch(url, options);
  if (response.getResponseCode() !== 200) return articles;
  
  const json = JSON.parse(response.getContentText());
  const items = json.items || [];
  
  for (let item of items) {
    let title = cleanHtmlText(item.title);
    let description = cleanHtmlText(item.description);
    const link = item.link;
    
    if (!title || !link) continue;
    
    let hasExclude = false;
    for (let ex of excludeKeywords) {
      if (title.indexOf(ex) !== -1 || description.indexOf(ex) !== -1) {
        hasExclude = true;
        break;
      }
    }
    if (hasExclude) continue;
    
    const originalLink = item.originallink || "";
    const isExclusive = title.indexOf("단독") !== -1;
    const isYonhap = link.indexOf("yna.co.kr") !== -1 || originalLink.indexOf("yna.co.kr") !== -1;
    
    if (!isYonhap && !isExclusive) continue;
    
    let determinedSource = getMediaNameFromUrl(link) || getMediaNameFromUrl(originalLink);
    if (!determinedSource) {
      determinedSource = isYonhap ? "연합뉴스" : "온라인";
    }
    
    articles.push({
      "date": todayStr,
      "published_at": Utilities.formatDate(new Date(item.pubDate), "GMT+09:00", "yyyy-MM-dd HH:mm:ss"),
      "source": determinedSource,
      "article_type": isYonhap ? "통신" : "온라인",
      "paper_section": "API검색",
      "title": title,
      "url": link,
      "summary": description,
      "body": "",
      "crawl_source": "api",
      "selected_for_report": "FALSE"
    });
  }
  
  return articles;
}

/**
 * Naver News 검색 API를 이용하여 언론사 원본 링크를 네이버 뉴스(n.news.naver.com) 제휴 기사 URL로 변환합니다.
 */
function convertToNaverNewsUrl(originalUrl, title, clientId, secret) {
  if (!originalUrl) return "";
  if (originalUrl.indexOf("news.naver.com") !== -1 || originalUrl.indexOf("n.news.naver.com") !== -1) {
    return originalUrl;
  }
  if (!clientId || !secret) {
    return originalUrl;
  }
  
  // 검색어 정제 (단독 태그, 괄호 등 제거)
  const cleanTitle = title
    .replace(/\[단독\]/g, "")
    .replace(/【.*?】/g, "")
    .replace(/\(.*?\)/g, "")
    .replace(/[^가-힣a-zA-Z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
    
  if (cleanTitle.length < 5) return originalUrl;
  
  try {
    const searchUrl = "https://openapi.naver.com/v1/search/news.json?query=" + encodeURIComponent(cleanTitle) + "&display=10&sort=sim";
    const options = {
      "headers": {
        "X-Naver-Client-Id": clientId,
        "X-Naver-Client-Secret": secret
      },
      "muteHttpExceptions": true,
      "timeout": 5000
    };
    
    const response = UrlFetchApp.fetch(searchUrl, options);
    if (response.getResponseCode() === 200) {
      const json = JSON.parse(response.getContentText());
      const items = json.items || [];
      
      for (let item of items) {
        const naverLink = item.link || "";
        const originLink = item.originallink || "";
        
        if (naverLink.indexOf("news.naver.com") !== -1 || naverLink.indexOf("n.news.naver.com") !== -1) {
          // 1. 원본 링크가 일치하는지 비교
          const normOriginal = originalUrl.replace(/^https?:\/\/(www\.)?/, "").split("?")[0].replace(/\/$/, "");
          const normOriginItem = originLink.replace(/^https?:\/\/(www\.)?/, "").split("?")[0].replace(/\/$/, "");
          
          if (normOriginal === normOriginItem) {
            Logger.log("URL 변환 성공 (원본 일치): " + originalUrl + " -> " + naverLink);
            return naverLink;
          }
          
          // 2. 제목 유사도 비교
          const cleanItemTitle = cleanHtmlText(item.title);
          if (getSimilarity(title, cleanItemTitle) > 0.6) {
            Logger.log("URL 변환 성공 (유사도 일치): " + originalUrl + " -> " + naverLink);
            return naverLink;
          }
        }
      }
    }
  } catch(e) {
    Logger.log("네이버 뉴스 URL 변환 실패: " + e);
  }
  
  return originalUrl;
}

// 1차 키워드 필터링 및 본문 스크래핑
function filterArticles(articles, keywords, excludes, existingUrls, clientId, clientSecret, startLimit, endLimit) {
  const result = [];
  const seenUrls = new Set();
  
  for (let art of articles) {
    if (seenUrls.has(art.url)) continue;
    seenUrls.add(art.url);
    
    // 기사 발행 시간 검증
    const artDate = parseArticleDate(art);
    let inRange = true;
    
    if (art.article_type !== "지면") {
      if (startLimit && artDate && artDate < startLimit) inRange = false;
      if (endLimit && artDate && artDate > endLimit) inRange = false;
    } else {
      // 지면 기사는 날짜 기준으로만 범위 필터링
      if (startLimit) {
        const startLimitDay = new Date(startLimit.getFullYear(), startLimit.getMonth(), startLimit.getDate());
        if (artDate && artDate < startLimitDay) inRange = false;
      }
      if (endLimit) {
        const endLimitDay = new Date(endLimit.getFullYear(), endLimit.getMonth(), endLimit.getDate(), 23, 59, 59);
        if (artDate && artDate > endLimitDay) inRange = false;
      }
    }
    
    // 사용자가 지정한 크롤링 시간 범위 밖에 위치한 기사는 완전히 스킵하여 제외합니다.
    if (!inRange) continue;
    
    // 이미 Raw_Articles 시트에 저장되어 있는 기존 기사라면:
    // 이미 body와 키워드 필터링이 완료되어 셀에 들어간 기사이므로,
    // 중복해서 웹 본문 스크래핑을 실행하지 않고 즉시 통과 리스트에 포함시킵니다.
    if (existingUrls && existingUrls.has(art.url)) {
      result.push(art);
      continue;
    }
    
    // 신규 수집 기사의 경우에만 키워드 및 제외 키워드 필터링을 수행합니다.
    let hasExclude = false;
    for (let ex of excludes) {
      if (art.title.indexOf(ex) !== -1 || art.summary.indexOf(ex) !== -1) {
        hasExclude = true;
        break;
      }
    }
    if (hasExclude) continue;
    
    let hasInclude = false;
    for (let kw of keywords) {
      if (art.title.indexOf(kw) !== -1 || art.summary.indexOf(kw) !== -1) {
        hasInclude = true;
        break;
      }
    }
    
    if (hasInclude) {
      // 본문 수집 전에 YNA, Hankyoreh 등 차단 가능성 높은 외부 기사 네이버 뉴스로 변환 시도
      if (clientId && clientSecret) {
        art.url = convertToNaverNewsUrl(art.url, art.title, clientId, clientSecret);
      }
      
      try {
        const fetchResult = fetchArticleBody(art.url);
        art.body = fetchResult.body;
        if (fetchResult.source && (art.source === "온라인" || art.source === "api" || !art.source)) {
          art.source = fetchResult.source;
        }
        if (!art.body) art.body = art.summary;
        result.push(art);
      } catch(e) {
        Logger.log("본문 수집 에러 (" + art.title + "): " + e);
        art.body = art.summary;
        result.push(art);
      }
      Utilities.sleep(100);
    }
  }
  return result;
}

// 기사 본문 파서 (언론사별 본문 영역 HTML 태그/클래스 매핑 버전)
function fetchArticleBody(url) {
  const options = {
    "muteHttpExceptions": true,
    "headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    },
    "followRedirects": true
  };
  
  let response;
  try {
    response = UrlFetchApp.fetch(url, options);
  } catch(e) {
    Logger.log("URL 호출 실패 (" + url + "): " + e);
    return { body: "", source: "" };
  }
  
  if (response.getResponseCode() !== 200) return { body: "", source: "" };
  
  // 인코딩 대응
  let html = "";
  try {
    html = response.getContentText("utf-8");
  } catch(e) {
    try {
      html = response.getContentText("euc-kr");
    } catch(e2) {
      html = response.getContentText();
    }
  }
  
  // 1. 매체명(언론사명) 추출 시도
  let extractedSource = getMediaNameFromUrl(url);
  
  // 만약 URL 매핑으로 찾지 못했다면 HTML 파싱 시도
  if (!extractedSource && html) {
    if (url.indexOf("naver.com") !== -1) {
      const logoMatch = html.match(/class=["'](?:media_end_head_top_logo|press_logo)["'][^>]*>[\s\S]*?<img[^>]*>/i);
      if (logoMatch) {
        const imgTag = logoMatch[0];
        const titleAttr = imgTag.match(/title=["']([^"']+)["']/i);
        const altAttr = imgTag.match(/alt=["']([^"']+)["']/i);
        if (titleAttr) extractedSource = titleAttr[1];
        else if (altAttr) extractedSource = altAttr[1];
      }
      
      if (!extractedSource) {
        const imgLogoMatch = html.match(/<img[^>]*class=["']press_logo["'][^>]*>/i);
        if (imgLogoMatch) {
          const titleAttr = imgLogoMatch[0].match(/title=["']([^"']+)["']/i) || imgLogoMatch[0].match(/alt=["']([^"']+)["']/i);
          if (titleAttr) extractedSource = titleAttr[1];
        }
      }
    }
    
    if (!extractedSource) {
      const ogSiteMatch = html.match(/<meta[^>]*property=["']og:site_name["'][^>]*content=["']([^"']+)["']/i) ||
                          html.match(/<meta[^>]*content=["']([^"']+)["'][^>]*property=["']og:site_name["']/i);
      if (ogSiteMatch) {
        const siteName = ogSiteMatch[1];
        if (siteName !== "네이버 뉴스" && siteName !== "Naver News") {
          extractedSource = siteName;
        }
      }
    }
  }
  
  if (extractedSource) {
    extractedSource = decodeHtmlEntities(extractedSource).trim();
  }
  
  let match = null;
  let bodyHtml = "";
  
  // 각 언론사별 기사 본문 영역 정규식 매핑
  // 1. 네이버 뉴스 (news.naver.com / n.news.naver.com) - 지면 기사 통합 대응
  if (url.indexOf("news.naver.com") !== -1) {
    match = /<article[^>]*id=["']dic_area["'][^>]*>([\s\S]*?)<\/article>/i.exec(html) ||
            /<div[^>]*id=["'](articeBody|articleBodyContents)["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }
  // 2. 연합뉴스 (yna.co.kr)
  else if (url.indexOf("yna.co.kr") !== -1) {
    match = /<article[^>]*class=["']story-news[^"']*["'][^>]*>([\s\S]*?)<\/article>/i.exec(html) ||
            /<div[^>]*class=["']story-news["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }
  // 3. 뉴시스 (newsis.com)
  else if (url.indexOf("newsis.com") !== -1) {
    match = /<article[^>]*id=["']articleBody["'][^>]*>([\s\S]*?)<\/article>/i.exec(html) ||
            /<div[^>]*id=["']articleBody["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }
  // 4. 조선일보 (chosun.com)
  else if (url.indexOf("chosun.com") !== -1) {
    match = /<section[^>]*class=["']article-body[^"']*["'][^>]*>([\s\S]*?)<\/section>/i.exec(html) ||
            /<div[^>]*class=["']article-body[^"']*["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }
  // 5. 중앙일보 (joongang.co.kr / joins.com)
  else if (url.indexOf("joongang.co.kr") !== -1 || url.indexOf("joins.com") !== -1) {
    match = /<div[^>]*id=["']article_body["'][^>]*>([\s\S]*?)<\/div>/i.exec(html) ||
            /<div[^>]*class=["']article_body[^"']*["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }
  // 6. 동아일보 (donga.com)
  else if (url.indexOf("donga.com") !== -1) {
    match = /<div[^>]*class=["']article_txt[^"']*["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }
  // 7. 한겨레 (hani.co.kr)
  else if (url.indexOf("hani.co.kr") !== -1) {
    match = /<div[^>]*class=["']text[^"']*["'][^>]*>([\s\S]*?)<\/div>/i.exec(html) ||
            /<div[^>]*class=["']article-text[^"']*["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }
  // 8. 경향신문 (khan.co.kr)
  else if (url.indexOf("khan.co.kr") !== -1) {
    match = /<div[^>]*class=["']art_body[^"']*["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }
  // 9. 서울신문 (seoul.co.kr)
  else if (url.indexOf("seoul.co.kr") !== -1) {
    match = /<div[^>]*id=["'](atic_txt|article_content)["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }
  // 10. 세계일보 (segye.com)
  else if (url.indexOf("segye.com") !== -1) {
    match = /<div[^>]*id=["'](articleBody|w_article_desc)["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }
  // 11. 국민일보 (kmib.co.kr)
  else if (url.indexOf("kmib.co.kr") !== -1) {
    match = /<div[^>]*id=["']articleBody["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }
  // 12. 한국일보 (hankookilbo.com)
  else if (url.indexOf("hankookilbo.com") !== -1) {
    match = /<div[^>]*class=["']editor-doc[^"']*["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }
  // 13. 문화일보 (munhwa.com)
  else if (url.indexOf("munhwa.com") !== -1) {
    match = /<div[^>]*id=["']NewsBody["'][^>]*>([\s\S]*?)<\/div>/i.exec(html);
  }

  // 매체별 본문 영역 매칭 성공 시 해당 부위 추출 및 노이즈 제거
  if (match) {
    bodyHtml = match[1];
    bodyHtml = bodyHtml.replace(/<script[\s\S]*?<\/script>/gi, "");
    bodyHtml = bodyHtml.replace(/<style[\s\S]*?<\/style>/gi, "");
    bodyHtml = bodyHtml.replace(/<em[^>]*class=["']img_desc["'][^>]*>[\s\S]*?<\/em>/gi, "");
    return {
      body: cleanHtmlText(bodyHtml),
      source: extractedSource
    };
  }
  
  // 14. 범용 파서 (위 매체 목록에 없거나 전용 파싱에 실패했을 때 작동)
  // 스크립트, 스타일, 헤더, 푸터, 네비게이션 태그 등을 날리고 p 태그 문장들만 모아 추출
  let cleanHtml = html
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<header[\s\S]*?<\/header>/gi, "")
    .replace(/<footer[\s\S]*?<\/footer>/gi, "")
    .replace(/<nav[\s\S]*?<\/nav>/gi, "")
    .replace(/<!--[\s\S]*?-->/g, "");
    
  const pRegex = /<p[^>]*>([\s\S]*?)<\/p>/gi;
  let pMatch;
  let paragraphs = [];
  while ((pMatch = pRegex.exec(cleanHtml)) !== null) {
    let pText = cleanHtmlText(pMatch[1]);
    if (pText.length > 25 && 
        pText.indexOf("Copyright") === -1 && 
        pText.indexOf("전재 및 재배포 금지") === -1 &&
        pText.indexOf("@") === -1) {
      paragraphs.push(pText);
    }
  }
  
  if (paragraphs.length > 0) {
    return {
      body: paragraphs.join("\n\n"),
      source: extractedSource
    };
  }
  
  return {
    body: cleanHtmlText(cleanHtml),
    source: extractedSource
  };
}

// 중복 기사 제거 및 우선순위 선정
function deduplicateArticles(articles) {
  const unique = [];
  
  articles.forEach(art => {
    let score = 10;
    if (art.title.indexOf("단독") !== -1) score = 1;
    else if (art.article_type === "지면") score = 2;
    else if (art.source === "연합뉴스") score = 3;
    else if (art.article_type === "통신") score = 4;
    art.priority = score;
  });
  
  articles.sort((a, b) => a.priority - b.priority);
  
  for (let art of articles) {
    let isDuplicate = false;
    for (let u of unique) {
      if (getSimilarity(art.title, u.title) > 0.5) {
        isDuplicate = true;
        break;
      }
    }
    if (!isDuplicate) {
      art.selected_for_report = "TRUE";
      unique.push(art);
    } else {
      art.selected_for_report = "FALSE";
      unique.push(art);
    }
  }
  
  return unique;
}

// 자카드 유사도
function getSimilarity(s1, s2) {
  const n1 = normalizeText(s1);
  const n2 = normalizeText(s2);
  const set1 = new Set(n1.split(" "));
  const set2 = new Set(n2.split(" "));
  
  const intersection = new Set([...set1].filter(x => set2.has(x)));
  const union = new Set([...set1, ...set2]);
  if (union.size === 0) return 0;
  return intersection.size / union.size;
}

function normalizeText(text) {
  return text.replace(/[\W_]+/g, " ").trim();
}

// HTML 엔티티 및 특수 기호, 줄바꿈 제거 청소기
function cleanHtmlText(text) {
  if (!text) return "";
  
  // 1. HTML 엔티티 및 NCR 디코딩 (&#10;, &middot;, &ldquo;, &#39; 등 대응)
  let decoded = decodeHtmlEntities(text);
  
  // 2. HTML 태그 제거
  decoded = decoded.replace(/<[^>]+>/g, " ");
  
  // 3. 보도용 기사 내 특수 지시 기호 제거 (▲, ▶, ◆, ■, ●, ◀, ▽, ▼ 등)
  decoded = decoded.replace(/[▲▶◆■●◀▽▼○◎☆★□◇]/g, "");
  
  // 4. 문장별 분할하여 관련 기사/광고성 푸터/헤더 제거
  const lines = decoded.split(/[\r\n]+/);
  const cleanedLines = [];
  let isFirstLine = true;
  
  for (let line of lines) {
    let trimmedLine = line.trim();
    if (!trimmedLine) continue;
    
    // 첫 줄이 아닌데 대괄호로 시작하는 뉴스 헤더(관련기사 목록)는 스킵
    if (!isFirstLine && /^[\[\(][가-힣\w\s&·“”‘’'\"#\-]+[\]\)]/.test(trimmedLine)) {
      continue;
    }
    
    // 특정 푸터 광고성 문구 제거
    if (trimmedLine.indexOf("후원금을 귀하게") !== -1 ||
        trimmedLine.indexOf("무단전재") !== -1 ||
        trimmedLine.indexOf("재배포 금지") !== -1 ||
        trimmedLine.indexOf("저작권자") !== -1 ||
        trimmedLine.indexOf("제보는 카카오톡") !== -1 ||
        trimmedLine.indexOf("많이 본 뉴스") !== -1) {
      continue;
    }
    
    isFirstLine = false;
    cleanedLines.push(trimmedLine);
  }
  
  decoded = cleanedLines.join(" ");
  
  // 5. 문장부호 정밀 정제
  decoded = decoded.replace(/,+[.]+/g, "."); // ",." or ",,." -> "."
  decoded = decoded.replace(/[.]+,+/g, "."); // ".," -> "."
  decoded = decoded.replace(/""/g, '"');      // "" -> "
  decoded = decoded.replace(/,+/g, ",");       // ,, -> ,
  decoded = decoded.replace(/\s+/g, " ");      // 연속된 공백 -> 단일 공백
  
  return decoded.trim();
}

/**
 * HTML Numeric Character References (NCR) 및 일반 엔티티를 디코딩합니다.
 */
function decodeHtmlEntities(text) {
  if (!text) return "";
  
  // 1. 일반 Named 엔티티 변환
  let decoded = text
    .replace(/&middot;/g, "·")
    .replace(/&ldquo;/g, '"')
    .replace(/&rdquo;/g, '"')
    .replace(/&lsquo;/g, "'")
    .replace(/&rsquo;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ');
    
  // 2. NCR (Numeric Character Reference) 디코딩
  decoded = decoded.replace(/&#(\d+);/g, function(match, dec) {
    return String.fromCharCode(parseInt(dec, 10));
  });
  
  decoded = decoded.replace(/&#x([0-9a-f]+);/gi, function(match, hex) {
    return String.fromCharCode(parseInt(hex, 16));
  });
  
  return decoded;
}

/**
 * 기사의 발행 시간(KST)을 파싱합니다.
 */
function parseArticleDate(art) {
  if (art.published_at) {
    const d = parseKstDateString(art.published_at);
    if (d && !isNaN(d.getTime())) return d;
  }
  if (art.date) {
    const cleanDate = normalizeYmd(art.date);
    if (cleanDate.length === 8) {
      const y = parseInt(cleanDate.substring(0, 4), 10);
      const m = parseInt(cleanDate.substring(4, 6), 10) - 1;
      const d = parseInt(cleanDate.substring(6, 8), 10);
      return new Date(y, m, d);
    }
  }
  return null;
}

/**
 * 시간 및 날짜 필터 기준시(KST)를 반환합니다.
 */
function getLimitDate(dateStr, timeStr, isEnd) {
  if (!dateStr) return null;
  const y = parseInt(dateStr.substring(0, 4), 10);
  const m = parseInt(dateStr.substring(4, 6), 10) - 1;
  const d = parseInt(dateStr.substring(6, 8), 10);
  
  let hh = isEnd ? 23 : 0;
  let mm = isEnd ? 59 : 0;
  let ss = isEnd ? 59 : 0;
  
  if (timeStr && timeStr.indexOf(":") !== -1) {
    const parts = timeStr.split(":");
    hh = parseInt(parts[0], 10);
    mm = parseInt(parts[1], 10);
    ss = 0;
  }
  
  return new Date(y, m, d, hh, mm, ss);
}

// 구글 시트에 데이터 쓰기
function writeToSpreadsheet(sheet, articles, config) {
  const wsRaw = sheet.getSheetByName("Raw_Articles");
  const wsReport = sheet.getSheetByName("Morning_Report");
  
  if (!wsRaw || !wsReport) return;
  
  const rawLastRow = wsRaw.getLastRow();
  const rawLastCol = wsRaw.getLastColumn();
  const reportLastCol = wsReport.getLastColumn();
  
  // 1. Raw_Articles 동적 컬럼 헤더 매핑
  const rawHeaders = wsRaw.getRange(1, 1, 1, rawLastCol).getValues()[0].map(h => String(h).trim());
  const getRawIdx = (names) => {
    for (let name of names) {
      const idx = rawHeaders.indexOf(name);
      if (idx !== -1) return idx;
    }
    return -1;
  };
  
  const rIdxDate = getRawIdx(["날짜", "date"]);
  const rIdxPub = getRawIdx(["발행시간", "published_at"]);
  const rIdxSrc = getRawIdx(["매체", "언론사", "source"]);
  const rIdxType = getRawIdx(["유형", "article_type"]);
  const rIdxSect = getRawIdx(["지면섹션", "출처", "섹션"]);
  const rIdxTitle = getRawIdx(["제목", "title"]);
  const rIdxUrl = getRawIdx(["URL", "url", "link"]);
  const rIdxSum = getRawIdx(["요약", "summary"]);
  const rIdxBody = getRawIdx(["내용", "본문", "body"]);
  const rIdxCrawlSrc = getRawIdx(["수집경로", "crawl_source"]);
  const rIdxStatus = getRawIdx(["선택여부", "selected_for_report"]);
  
  // 2. Morning_Report 동적 컬럼 헤더 매핑
  const reportHeaders = wsReport.getRange(1, 1, 1, reportLastCol).getValues()[0].map(h => String(h).trim());
  const getRepIdx = (names) => {
    for (let name of names) {
      const idx = reportHeaders.indexOf(name);
      if (idx !== -1) return idx;
    }
    return -1;
  };
  
  const repIdxSelect = getRepIdx(["선택", "select"]);
  const repIdxDate = getRepIdx(["날짜", "date"]);
  const repIdxTitle = getRepIdx(["제목", "title"]);
  const repIdxSrc = getRepIdx(["매체", "언론사", "source"]);
  const repIdxUrl = getRepIdx(["URL", "url", "link"]);
  const repIdxBody = getRepIdx(["내용", "본문", "body"]);
  const repIdxSect = getRepIdx(["출처", "지면섹션", "섹션"]);
  
  const rawRows = [];
  const reportRows = [];
  
  articles.forEach(art => {
    const cleanTitle = cleanHtmlText(art.title);
    const cleanSummary = cleanHtmlText(art.summary);
    const cleanBody = cleanHtmlText(art.body || art.summary);
    const mediaSource = art.source ? String(art.source).trim() : "온라인";
    
    // Raw_Articles 로우 조립
    const rawData = [];
    for (let i = 0; i < rawLastCol; i++) rawData[i] = "";
    if (rIdxDate !== -1) rawData[rIdxDate] = art.date;
    if (rIdxPub !== -1) rawData[rIdxPub] = art.published_at;
    if (rIdxSrc !== -1) rawData[rIdxSrc] = mediaSource;
    if (rIdxType !== -1) rawData[rIdxType] = art.article_type;
    if (rIdxSect !== -1) rawData[rIdxSect] = art.paper_section;
    if (rIdxTitle !== -1) rawData[rIdxTitle] = cleanTitle;
    if (rIdxUrl !== -1) rawData[rIdxUrl] = art.url;
    if (rIdxSum !== -1) rawData[rIdxSum] = cleanSummary;
    if (rIdxBody !== -1) rawData[rIdxBody] = cleanBody.substring(0, 30000);
    if (rIdxCrawlSrc !== -1) rawData[rIdxCrawlSrc] = art.crawl_source;
    if (rIdxStatus !== -1) rawData[rIdxStatus] = art.selected_for_report;
    rawRows.push(rawData);
    
    // Morning_Report 로우 조립
    if (art.selected_for_report === "TRUE") {
      const reportData = [];
      for (let i = 0; i < reportLastCol; i++) reportData[i] = "";
      if (repIdxSelect !== -1) reportData[repIdxSelect] = true;
      if (repIdxDate !== -1) reportData[repIdxDate] = art.date;
      if (repIdxTitle !== -1) reportData[repIdxTitle] = cleanTitle;
      if (repIdxSrc !== -1) reportData[repIdxSrc] = mediaSource;
      if (repIdxUrl !== -1) reportData[repIdxUrl] = art.url;
      if (repIdxBody !== -1) reportData[repIdxBody] = cleanBody;
      if (repIdxSect !== -1) reportData[repIdxSect] = art.paper_section;
      reportRows.push(reportData);
    }
  });
  
  // Raw_Articles 기록 (신규 기사 중 시트에 없는 기사만 아래로 누적)
  if (rawRows.length > 0) {
    const rawExistingUrls = getExistingUrls(sheet);
    const uniqueRawRows = rawRows.filter(row => {
      const urlVal = rIdxUrl !== -1 ? row[rIdxUrl] : "";
      return urlVal ? !rawExistingUrls.has(urlVal) : true;
    });
    if (uniqueRawRows.length > 0) {
      wsRaw.getRange(rawLastRow + 1, 1, uniqueRawRows.length, rawLastCol).setValues(uniqueRawRows);
    }
  }
  
  // Morning_Report 모드 처리 (새로 쓰기 vs 과거 기사 유지) 및 기록
  if (reportRows.length > 0) {
    let reportStartRow = wsReport.getLastRow() + 1;
    
    if (config.morningReportMode === "새로 쓰기") {
      const lastRow = wsReport.getLastRow();
      if (lastRow > 1) {
        wsReport.getRange(2, 1, lastRow - 1, reportLastCol).clearContent().clearFormat();
      }
      reportStartRow = 2; // 초기화한 경우 2번째 행부터 새로 기재
    }
    
    const targetRange = wsReport.getRange(reportStartRow, 1, reportRows.length, reportLastCol);
    targetRange.setValues(reportRows);
    
    // 선택 열에 체크박스 설정
    if (repIdxSelect !== -1) {
      const checkboxRange = wsReport.getRange(reportStartRow, repIdxSelect + 1, reportRows.length, 1);
      checkboxRange.insertCheckboxes();
    }
  }
}

/**
 * 스프레드시트가 열릴 때 상단 메뉴를 자동으로 추가합니다.
 */
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('📰 아침보고 관리')
    .addItem('▶ 뉴스 크롤링 즉시 실행', 'showCrawlDialog')
    .addItem('🚀 아침보고서(n8n) 생성 및 전송', 'triggerN8nReport')
    .addToUi();
}

/**
 * 사용자가 메뉴를 클릭했을 때 알림창을 띄우고 크롤링을 수행합니다.
 * 하위 호환성을 위해 showCrawlDialog를 호출하도록 우회 처리합니다.
 */
function runCrawlWithAlert() {
  showCrawlDialog();
}

/**
 * 날짜, 시간 필터, 적재 모드를 직관적으로 조절하고 실행할 수 있는 HTML 대화상자를 띄웁니다.
 */
function showCrawlDialog() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet();
  const config = loadConfig(sheet);
  
  // YYYYMMDD -> YYYY-MM-DD 포맷 변환
  const formatDash = function(ymd) {
    if (!ymd || ymd.length !== 8) return "";
    return ymd.substring(0, 4) + "-" + ymd.substring(4, 6) + "-" + ymd.substring(6, 8);
  };
  
  // 오늘 날짜 YYYY-MM-DD
  const today = new Date();
  const getTodayDash = function(d) {
    const y = d.getFullYear();
    const m = ('0' + (d.getMonth() + 1)).slice(-2);
    const date = ('0' + d.getDate()).slice(-2);
    return y + "-" + m + "-" + date;
  };
  const todayDash = getTodayDash(today);
  
  // 구글 시트 셀 서식에 따라 Date 객체로 로드되는 시간 표준화 헬퍼
  const formatTimeHelper = function(val) {
    if (!val) return "";
    if (val instanceof Date) {
      const h = ('0' + val.getHours()).slice(-2);
      const m = ('0' + val.getMinutes()).slice(-2);
      return h + ":" + m;
    }
    const strVal = String(val).trim();
    const matches = strVal.match(/(\d{2}):(\d{2})/);
    if (matches) {
      return matches[1] + ":" + matches[2];
    }
    return strVal;
  };
  
  // Config 값 파싱 혹은 기본값 지정
  const startVal = formatDash(config.startDate) || todayDash;
  const endVal = formatDash(config.endDate) || todayDash;
  const startTimeVal = formatTimeHelper(config.startTime) || "18:00";
  const endTimeVal = formatTimeHelper(config.endTime) || "06:00";
  const modeVal = config.morningReportMode || "유지";
  
  // HTML 템플릿 로드
  const template = HtmlService.createTemplate(getDialogHtmlContent());
  template.startDate = startVal;
  template.endDate = endVal;
  template.startTime = startTimeVal;
  template.endTime = endTimeVal;
  template.morningReportMode = modeVal;
  
  const htmlOutput = template.evaluate()
      .setWidth(450)
      .setHeight(500)
      .setTitle('뉴스 크롤링 설정 및 실행');
      
  SpreadsheetApp.getUi().showModalDialog(htmlOutput, '뉴스 크롤링 설정');
}

/**
 * HTML 모달 팝업으로부터 전달된 설정값을 받아 크롤링을 처리합니다.
 */
function runCrawlWithParams(params) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet();
  
  if (params && params.saveToConfig) {
    const ws = sheet.getSheetByName("Config");
    if (ws) {
      // H2 ~ L2 셀에 값을 써서 저장합니다.
      // H열(8): startDate, I열(9): endDate, J열(10): startTime, K열(11): endTime, L열(12): morningReportMode
      ws.getRange(2, 8).setValue(params.startDate);
      ws.getRange(2, 9).setValue(params.endDate);
      ws.getRange(2, 10).setValue(params.startTime);
      ws.getRange(2, 11).setValue(params.endTime);
      ws.getRange(2, 12).setValue(params.morningReportMode);
      SpreadsheetApp.flush();
    }
  }
  
  try {
    sheet.toast('뉴스 수집을 시작합니다. 잠시만 기다려 주세요...', '크롤링 진행 중', -1);
    runCrawl(params);
    sheet.toast('크롤링 및 시트 적재가 성공적으로 완료되었습니다!', '수집 완료', 5);
    return "SUCCESS";
  } catch (e) {
    Logger.log("크롤링 오류: " + e);
    sheet.toast('크롤링 중 오류가 발생했습니다: ' + e.toString(), '수집 실패', 10);
    throw new Error(e.toString());
  }
}

/**
 * 모달 팝업용 HTML 마크업 컨텐츠 문자열을 반환합니다.
 */
function getDialogHtmlContent() {
  return `<!DOCTYPE html>
<html>
<head>
  <base target="_top">
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <script>
    window.onerror = function(message, source, lineno, colno, error) {
      alert("화면 오류가 발생했습니다: " + message + " [라인: " + lineno + ", 소스: " + source + "]");
      return false;
    };
  </script>
  <style>
    :root {
      --bg-color: #0f172a;
      --card-bg: rgba(30, 41, 59, 0.7);
      --primary-color: #6366f1;
      --primary-hover: #4f46e5;
      --border-color: rgba(255, 255, 255, 0.08);
      --text-main: #f8fafc;
      --text-sub: #94a3b8;
      --shadow-indigo: rgba(99, 102, 241, 0.3);
    }
    
    body {
      margin: 0;
      padding: 20px;
      background-color: var(--bg-color);
      color: var(--text-main);
      font-family: 'Outfit', -apple-system, sans-serif;
      font-size: 13px;
      box-sizing: border-box;
      overflow: hidden;
    }
    
    .header {
      margin-bottom: 20px;
      text-align: center;
    }
    
    .header h2 {
      margin: 0 0 4px 0;
      font-size: 20px;
      font-weight: 600;
      background: linear-gradient(135deg, #a5b4fc, #818cf8, #6366f1);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    
    .header p {
      margin: 0;
      font-size: 12px;
      color: var(--text-sub);
    }
    
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 16px;
      box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);
      backdrop-filter: blur(10px);
      margin-bottom: 20px;
    }
    
    .preset-section {
      margin-bottom: 16px;
    }
    
    .preset-label {
      font-weight: 500;
      color: var(--text-sub);
      margin-bottom: 8px;
      display: block;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    
    .preset-buttons {
      display: flex;
      gap: 8px;
    }
    
    .btn-preset {
      flex: 1;
      padding: 8px;
      background-color: rgba(99, 102, 241, 0.1);
      border: 1px solid rgba(99, 102, 241, 0.2);
      border-radius: 6px;
      color: #818cf8;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    
    .btn-preset:hover {
      background-color: var(--primary-color);
      color: white;
      border-color: var(--primary-color);
      box-shadow: 0 0 10px var(--shadow-indigo);
    }
    
    .form-group {
      margin-bottom: 14px;
    }
    
    label {
      display: block;
      margin-bottom: 6px;
      font-weight: 500;
      color: var(--text-main);
    }
    
    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    
    input[type="date"],
    input[type="time"],
    select {
      width: 100%;
      padding: 8px 10px;
      background-color: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      color: var(--text-main);
      font-size: 13px;
      box-sizing: border-box;
      outline: none;
      transition: border-color 0.2s;
    }
    
    input[type="date"]:focus,
    input[type="time"]:focus,
    select:focus {
      border-color: var(--primary-color);
    }
    
    .checkbox-container {
      display: flex;
      align-items: center;
      margin-top: 10px;
      cursor: pointer;
      user-select: none;
    }
    
    .checkbox-container input {
      margin-right: 8px;
      accent-color: var(--primary-color);
      width: 16px;
      height: 16px;
    }
    
    .checkbox-container span {
      font-size: 12px;
      color: var(--text-sub);
    }
    
    .actions {
      display: flex;
      gap: 10px;
    }
    
    .btn {
      flex: 1;
      padding: 10px;
      border: none;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    
    .btn-primary {
      background: linear-gradient(135deg, var(--primary-color), var(--primary-hover));
      color: white;
      box-shadow: 0 4px 10px var(--shadow-indigo);
    }
    
    .btn-primary:hover {
      transform: translateY(-1px);
      box-shadow: 0 6px 14px var(--shadow-indigo);
    }
    
    .btn-secondary {
      background-color: transparent;
      border: 1px solid var(--border-color);
      color: var(--text-sub);
    }
    
    .btn-secondary:hover {
      background-color: rgba(255, 255, 255, 0.05);
      color: var(--text-main);
    }
    
    .loading-overlay {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background-color: rgba(15, 23, 42, 0.9);
      z-index: 100;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      backdrop-filter: blur(4px);
    }
    
    .spinner {
      width: 32px;
      height: 32px;
      border: 3px solid rgba(255, 255, 255, 0.1);
      border-radius: 50%;
      border-top-color: var(--primary-color);
      animation: spin 1s linear infinite;
      margin-bottom: 12px;
    }
    
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    
    .loading-text {
      font-weight: 500;
      color: var(--text-main);
      font-size: 13px;
    }
  </style>
</head>
<body>
  <div class="header">
    <h2>뉴스 크롤링 설정 및 실행</h2>
    <p>수집할 뉴스 날짜 및 시간 필터를 간편하게 지정하세요</p>
  </div>
  
  <div class="card">
    <!-- 빠른 설정 프리셋 -->
    <div class="preset-section">
      <span class="preset-label">시간 빠른 프리셋</span>
      <div class="preset-buttons">
        <button type="button" class="btn-preset" onclick="applyPreset(6)">최근 6시간</button>
        <button type="button" class="btn-preset" onclick="applyPreset(12)">최근 12시간</button>
        <button type="button" class="btn-preset" onclick="applyPreset(24)">최근 24시간</button>
      </div>
    </div>
    
    <!-- 날짜 설정 -->
    <div class="form-group grid-2">
      <div>
        <label for="startDate">시작일</label>
        <input type="date" id="startDate" value="<?= startDate ?>">
      </div>
      <div>
        <label for="endDate">종료일</label>
        <input type="date" id="endDate" value="<?= endDate ?>">
      </div>
    </div>
    
    <!-- 시간 설정 -->
    <div class="form-group grid-2">
      <div>
        <label for="startTime">시작 시간 (필터)</label>
        <input type="time" id="startTime" value="<?= startTime ?>">
      </div>
      <div>
        <label for="endTime">종료 시간 (필터)</label>
        <input type="time" id="endTime" value="<?= endTime ?>">
      </div>
    </div>
    
    <!-- 모드 설정 -->
    <div class="form-group grid-2" style="align-items: center;">
      <div>
        <label for="morningReportMode">적재 모드</label>
        <select id="morningReportMode">
          <option value="과거 기사 유지" <?= morningReportMode === '과거 기사 유지' ? 'selected' : '' ?>>과거 기사 유지 (누적 적재)</option>
          <option value="새로 쓰기" <?= morningReportMode === '새로 쓰기' ? 'selected' : '' ?>>새로 쓰기 (기존 기사 삭제)</option>
        </select>
      </div>
      <div style="padding-top: 18px;">
        <label class="checkbox-container">
          <input type="checkbox" id="saveToConfig" checked>
          <span>설정을 Config 탭에 저장</span>
        </label>
      </div>
    </div>
  </div>
  
  <div class="actions">
    <button type="button" class="btn btn-secondary" onclick="google.script.host.close()">취소</button>
    <button type="button" class="btn btn-primary" onclick="submitCrawl()">크롤링 시작</button>
  </div>
  
  <!-- 로딩 오버레이 -->
  <div id="loadingOverlay" class="loading-overlay">
    <div class="spinner"></div>
    <div class="loading-text">뉴스를 수집하고 있습니다. 잠시만 기다려 주세요...</div>
  </div>
  
  <script>
    function applyPreset(hours) {
      const now = new Date();
      
      // template literal 내의 backtick 및 escaping 교정
      function getFormattedDate(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const date = String(d.getDate()).padStart(2, '0');
        return y + '-' + m + '-' + date;
      }
      
      function getFormattedTime(d) {
        const h = String(d.getHours()).padStart(2, '0');
        const min = String(d.getMinutes()).padStart(2, '0');
        return h + ':' + min;
      }
      
      document.getElementById('endDate').value = getFormattedDate(now);
      document.getElementById('endTime').value = getFormattedTime(now);
      
      const past = new Date(now.getTime() - hours * 60 * 60 * 1000);
      document.getElementById('startDate').value = getFormattedDate(past);
      document.getElementById('startTime').value = getFormattedTime(past);
    }
    
    function submitCrawl() {
      const params = {
        startDate: document.getElementById('startDate').value.replace(/-/g, ""),
        endDate: document.getElementById('endDate').value.replace(/-/g, ""),
        startTime: document.getElementById('startTime').value,
        endTime: document.getElementById('endTime').value,
        morningReportMode: document.getElementById('morningReportMode').value,
        saveToConfig: document.getElementById('saveToConfig').checked
      };
      
      document.getElementById('loadingOverlay').style.display = 'flex';
      
      google.script.run
        .withSuccessHandler(onSuccess)
        .withFailureHandler(onFailure)
        .runCrawlWithParams(params);
    }
    
    function onSuccess(msg) {
      google.script.host.close();
    }
    
    function onFailure(err) {
      document.getElementById('loadingOverlay').style.display = 'none';
      alert('크롤링 중 에러가 발생했습니다: ' + err.message);
    }
  </script>
</body>
</html>`;
}

/**
 * 선택(체크)된 기사들로 n8n 아침보고 생성을 트리거합니다.
 */
function triggerN8nReport() {
  const ui = SpreadsheetApp.getUi();
  const sheet = SpreadsheetApp.getActiveSpreadsheet();
  const config = loadConfig(sheet);
  const webhookUrl = config.n8nWebhookUrl;
  
  if (!webhookUrl) {
    ui.alert('설정 오류', 'Config 시트 E2 셀에 n8n Webhook URL이 입력되지 않았습니다!\n(예: https://.../webhook/morning-report-trigger)', ui.ButtonSet.OK);
    return;
  }
  
  const response = ui.alert(
    '보고서 발행',
    '선택(체크)된 기사들로 아침보고서(n8n)를 즉시 생성 및 전송하시겠습니까?',
    ui.ButtonSet.YES_NO
  );
  
  if (response == ui.Button.YES) {
    sheet.toast('n8n 워크플로우를 호출 중입니다. 잠시만 기다려 주세요...', '발행 시작', -1);
    try {
      const options = {
        'method': 'post',
        'contentType': 'application/json',
        'payload': JSON.stringify({
          'action': 'generate_report',
          'timestamp': new Date().toISOString()
        }),
        'muteHttpExceptions': true
      };
      
      const res = UrlFetchApp.fetch(webhookUrl, options);
      const resCode = res.getResponseCode();
      
      if (resCode === 200 || resCode === 201) {
        sheet.toast('성공적으로 발행 요청이 완료되었습니다. 곧 텔레그램 메시지가 전송됩니다!', '발행 완료', 5);
      } else {
        ui.alert('발행 실패', 'n8n 호출 실패 (HTTP ' + resCode + '):\n' + res.getContentText(), ui.ButtonSet.OK);
      }
    } catch (e) {
      ui.alert('오류 발생', '호출 중 에러가 발생했습니다:\n' + e.toString(), ui.ButtonSet.OK);
    }
  }
}

/**
 * 텔레그램 알림을 직접 발송합니다.
 */
function sendTelegramNotification(token, chatId, sheetUrl) {
  const url = "https://api.telegram.org/bot" + token + "/sendMessage";
  const text = "📢 *[아침보고 뉴스 수집 완료]*\n\n오늘자 뉴스 수집이 완료되었습니다. 아래 스프레드시트 링크에서 기사를 확인 및 선택하신 후, 상단 맞춤 메뉴에서 발행해 주세요!\n\n🔗 [구글 스프레드시트 바로가기](" + sheetUrl + ")";
  
  const payload = {
    "chat_id": chatId,
    "text": text,
    "parse_mode": "Markdown"
  };
  
  const options = {
    "method": "post",
    "contentType": "application/json",
    "payload": JSON.stringify(payload),
    "muteHttpExceptions": true
  };
  
  UrlFetchApp.fetch(url, options);
}

/**
 * Raw_Articles 시트에서 특정 날짜 범위에 속하는 기존 기사들을 로드합니다.
 */
function loadExistingArticlesFromRaw(sheet, datesSet) {
  const articles = [];
  const ws = sheet.getSheetByName("Raw_Articles");
  if (!ws) return articles;
  
  const lastRow = ws.getLastRow();
  if (lastRow <= 1) return articles;
  
  const lastCol = ws.getLastColumn();
  const headers = ws.getRange(1, 1, 1, lastCol).getValues()[0].map(h => String(h).trim());
  
  // 헤더명을 감지하여 동적으로 열 인덱스 매핑 (없을 시 -1 반환)
  const getIdx = (names) => {
    for (let name of names) {
      const idx = headers.indexOf(name);
      if (idx !== -1) return idx;
    }
    return -1;
  };
  
  const idxDate = getIdx(["날짜", "date"]);
  const idxPub = getIdx(["발행시간", "published_at"]);
  const idxSrc = getIdx(["매체", "언론사", "source"]);
  const idxType = getIdx(["유형", "article_type"]);
  const idxSect = getIdx(["지면섹션", "출처", "섹션"]);
  const idxTitle = getIdx(["제목", "title"]);
  const idxUrl = getIdx(["URL", "url", "link"]);
  const idxSum = getIdx(["요약", "summary"]);
  const idxBody = getIdx(["내용", "본문", "body"]);
  const idxCrawlSrc = getIdx(["수집경로", "crawl_source"]);
  
  let idxReport = headers.indexOf("선택여부");
  if (idxReport === -1) idxReport = headers.indexOf("selected_for_report");
  
  const allValues = ws.getRange(2, 1, lastRow - 1, lastCol).getValues();
  
  for (let i = 0; i < allValues.length; i++) {
    const row = allValues[i];
    const dateVal = idxDate !== -1 ? row[idxDate] : "";
    const dateStr = normalizeYmd(dateVal);
    
    // 이번 크롤링 대상 날짜에 포함되는 기사만 로드
    if (datesSet.has(dateStr)) {
      articles.push({
        "date": dateStr,
        "published_at": (idxPub !== -1 && row[idxPub]) ? String(row[idxPub]).trim() : "",
        "source": (idxSrc !== -1 && row[idxSrc]) ? String(row[idxSrc]).trim() : "온라인",
        "article_type": (idxType !== -1 && row[idxType]) ? String(row[idxType]).trim() : "",
        "paper_section": (idxSect !== -1 && row[idxSect]) ? String(row[idxSect]).trim() : "",
        "title": (idxTitle !== -1 && row[idxTitle]) ? String(row[idxTitle]).trim() : "",
        "url": (idxUrl !== -1 && row[idxUrl]) ? String(row[idxUrl]).trim() : "",
        "summary": (idxSum !== -1 && row[idxSum]) ? String(row[idxSum]).trim() : "",
        "body": (idxBody !== -1 && row[idxBody]) ? String(row[idxBody]).trim() : "",
        "crawl_source": (idxCrawlSrc !== -1 && row[idxCrawlSrc]) ? String(row[idxCrawlSrc]).trim() : "",
        "selected_for_report": (idxReport !== -1 && row[idxReport]) ? String(row[idxReport]).trim() : "FALSE"
      });
    }
  }
  return articles;
}

/**
 * 다양한 날짜 형식(Date 객체, 문자열 포맷 등)을 YYYYMMDD 문자열로 변환합니다.
 */
function normalizeYmd(val) {
  if (!val) return "";
  if (val instanceof Date) {
    const y = val.getFullYear();
    const m = ('0' + (val.getMonth() + 1)).slice(-2);
    const date = ('0' + val.getDate()).slice(-2);
    return y + m + date;
  }
  
  const strVal = String(val).trim();
  const clean = strVal.replace(/[^0-9]/g, "");
  if (clean.length === 8) return clean;
  
  const d = new Date(strVal);
  if (!isNaN(d.getTime())) {
    const y = d.getFullYear();
    const m = ('0' + (d.getMonth() + 1)).slice(-2);
    const date = ('0' + d.getDate()).slice(-2);
    return y + m + date;
  }
  
  return clean;
}

/**
 * URL(원본 링크 또는 네이버 링크)을 분석하여 매체(언론사) 한글명을 추출합니다.
 * 매칭되지 않는 경우 빈 문자열 ""을 반환합니다.
 */
function getMediaNameFromUrl(url) {
  if (!url) return "";
  const lowerUrl = url.toLowerCase();
  
  // 1. 네이버 뉴스 URL인 경우 OID 추출하여 판별
  if (lowerUrl.indexOf("naver.com") !== -1) {
    const oidMatch = url.match(/article\/(\d+)/) || url.match(/oid=(\d+)/);
    if (oidMatch) {
      const oid = oidMatch[1];
      const oidMap = {
        "032": "경향신문",
        "005": "국민일보",
        "020": "동아일보",
        "021": "문화일보",
        "081": "서울신문",
        "022": "세계일보",
        "025": "중앙일보",
        "028": "한겨레",
        "469": "한국일보",
        "001": "연합뉴스",
        "003": "뉴시스",
        "079": "노컷뉴스",
        "055": "SBS",
        "437": "JTBC",
        "448": "TV조선",
        "056": "KBS",
        "214": "MBC",
        "052": "YTN",
        "023": "조선일보"
      };
      if (oidMap[oid]) return oidMap[oid];
    }
  }
  
  // 2. 일반 도메인 매핑
  const domainMap = {
    "khan.co.kr": "경향신문",
    "donga.com": "동아일보",
    "chosun.com": "조선일보",
    "joongang.co.kr": "중앙일보",
    "joins.com": "중앙일보",
    "hani.co.kr": "한겨레",
    "hankookilbo.com": "한국일보",
    "munhwa.com": "문화일보",
    "seoul.co.kr": "서울신문",
    "segye.com": "세계일보",
    "kmib.co.kr": "국민일보",
    "yna.co.kr": "연합뉴스",
    "newsis.com": "뉴시스",
    "nocutnews.co.kr": "노컷뉴스",
    "lawleader.co.kr": "로리더",
    "lec.co.kr": "법률저널",
    "lawtimes.co.kr": "법률신문",
    "sbs.co.kr": "SBS",
    "kbs.co.kr": "KBS",
    "imbc.com": "MBC",
    "jtbc.co.kr": "JTBC",
    "ichannela.com": "채널A",
    "tvchosun.com": "TV조선",
    "ytn.co.kr": "YTN",
    "hankyung.com": "한국경제",
    "mk.co.kr": "매일경제",
    "fnnews.com": "파이낸셜뉴스",
    "sedaily.com": "서울경제",
    "mt.co.kr": "머니투데이",
    "asiae.co.kr": "아시아경제",
    "heraldcorp.com": "헤럴드경제",
    "edaily.co.kr": "이데일리"
  };
  
  for (let domain in domainMap) {
    if (lowerUrl.indexOf(domain) !== -1) {
      return domainMap[domain];
    }
  }
  
  // 3. 맵에 없는 경우 호스트 네임 파싱
  try {
    const matches = lowerUrl.match(/^https?:\/\/([^\/?#]+)(?:[\/?#]|$)/i);
    if (matches && matches[1]) {
      let host = matches[1].replace("www.", "");
      return host;
    }
  } catch(e) {}
  
  return "";
}

/**
 * 한국어 '오전/오후'가 포함된 한글 로케일 날짜 및 범용 시간 문자열을 파싱합니다.
 */
function parseKstDateString(str) {
  if (!str) return null;
  if (str instanceof Date) return str;
  
  const s = String(str).trim();
  
  // 1. 일반 Date 파싱 시도
  let d = new Date(s);
  if (!isNaN(d.getTime())) return d;
  
  // 2. 한글 '오전/오후' 파싱 (예: "2026. 6. 7. 오후 3:30:00" 등)
  const ampmMatch = s.match(/(오전|오후)\s*(\d+):(\d+)(?::(\d+))?/);
  const dateNumbers = s.replace(/(오전|오후).*/, "").replace(/[^0-9]/g, " ").trim().split(/\s+/);
  
  if (ampmMatch && dateNumbers.length >= 3) {
    const year = parseInt(dateNumbers[0], 10);
    const month = parseInt(dateNumbers[1], 10) - 1;
    const day = parseInt(dateNumbers[2], 10);
    
    const isPm = ampmMatch[1] === "오후";
    let hour = parseInt(ampmMatch[2], 10);
    const min = parseInt(ampmMatch[3], 10);
    const sec = ampmMatch[4] ? parseInt(ampmMatch[4], 10) : 0;
    
    if (isPm && hour < 12) hour += 12;
    if (!isPm && hour === 12) hour = 0;
    
    d = new Date(year, month, day, hour, min, sec);
    if (!isNaN(d.getTime())) return d;
  }
  
  // 3. 순수 연속 숫자 형태 (예: "20260607153000")
  const clean = s.replace(/[^0-9]/g, "");
  if (clean.length >= 8) {
    const year = parseInt(clean.substring(0, 4), 10);
    const month = parseInt(clean.substring(4, 6), 10) - 1;
    const day = parseInt(clean.substring(6, 8), 10);
    const hour = clean.length >= 10 ? parseInt(clean.substring(8, 10), 10) : 0;
    const min = clean.length >= 12 ? parseInt(clean.substring(10, 12), 10) : 0;
    const sec = clean.length >= 14 ? parseInt(clean.substring(12, 14), 10) : 0;
    
    d = new Date(year, month, day, hour, min, sec);
    if (!isNaN(d.getTime())) return d;
  }
  
  return null;
}


