import type { OrderIntent } from "./types";

const koNumbers: Record<string, number> = {
  한: 1,
  두: 2,
  세: 3,
  네: 4,
  다섯: 5,
  하나: 1,
  둘: 2,
  셋: 3,
  넷: 4,
};

export function hasExplicitNoAllergies(input: string): boolean {
  return /^(?:(?:저|나)(?:는|은)?\s+)?(?:알레르기|알러지)(?:는|가|도)?\s*(?:전혀\s*)?없(?:어|어요|고|습니다|음)/.test(input.trim().toLowerCase());
}

export function parseIntent(input: string): OrderIntent {
  const text = input.trim().toLowerCase();
  const intent: OrderIntent = { action: "recommend" };
  if (/직원|사장님.*불러|help|staff/.test(text)) intent.action = "help";
  else if (/(?:추천한|이걸|그걸|이거|그거|첫\s*번째|두\s*번째|세\s*번째|[123]\s*번).*주문해(?:줘|주세요)?/.test(text)) intent.action = "add";
  else if (/결제할[게께]|결제해|계산할[게께]|계산해|주문\s*완료|이대로\s*주문|checkout|주문할[게께]|주문할래/.test(text) || /^\s*주문해(?:줘|주세요)?[.! ]*$/.test(text)) intent.action = "checkout";
  else if (/빼줘|삭제|제거|remove/.test(text) || (/빼고/.test(text) && /장바구니|카트|담은|첫\s*번째|두\s*번째|세\s*번째|[123]\s*번/.test(text))) intent.action = "remove";
  else if (/담아|추가|넣어|add /.test(text)) intent.action = "add";
  else if (/있어\?|얼마|가격|재료|뭐가/.test(text)) intent.action = "ask";
  const people = text.match(
    /(\d+|한|두|세|네|다섯|하나|둘|셋|넷)\s*(명|인|사람)/,
  );
  if (people) intent.peopleCount = Number(people[1]) || koNumbers[people[1]];
  if (!intent.peopleCount && /부모님.*(셋|세 명|3명)/.test(text))
    intent.peopleCount = 3;
  if (intent.peopleCount)
    intent.peopleCount = Math.min(12, Math.max(1, intent.peopleCount));
  const count = text.match(/(\d+|한|두|세|네|하나|둘|셋|넷)\s*(개|잔|그릇)/);
  if (count)
    intent.quantity = Math.min(30, Number(count[1]) || koNumbers[count[1]]);
  const man = text.match(/(\d+(?:\.\d+)?)\s*만\s*원/);
  const won = text.match(/([\d,]{4,})\s*원/);
  const under = text.match(/(?:under|below)\s*[₩w]?\s*([\d,]+)/);
  if (man) intent.totalBudget = Math.round(Number(man[1]) * 10000);
  else if (won) intent.totalBudget = Number(won[1].replaceAll(",", ""));
  else if (under) intent.totalBudget = Number(under[1].replaceAll(",", ""));
  else if (/(?:^|\s)만\s*원/.test(text)) intent.totalBudget = 10000;
  if (/절대.*(안|못).*맵|매운.*절대|매운.*못|맵지\s*않|안\s*매운|not spicy|no spice/.test(text))
    intent.maxSpiceLevel = 0;
  else if (/안 맵|덜 맵|순한|mild/.test(text)) intent.maxSpiceLevel = 1;
  if (/매운|매콤|얼큰|맵게/.test(text) && !/안\s*맵|맵지|매운.*(?:안|못)|맵찔/.test(text)) intent.minSpiceLevel = 2;
  intent.kidsOnly = /애기용|아기용|아이용|유아용|키즈\s*메뉴|어린이\s*메뉴/.test(text);
  intent.wantsWarm = /따뜻|뜨끈|국물|warm|hot/.test(text);
  intent.wantsCool = /시원|차가운|cold|cool/.test(text);
  intent.wantsMild = /안\s*맵|덜\s*맵|맵지\s*않|안\s*매운|순한|mild|not spicy/.test(text);
  intent.vegetarian = /채식|비건|vegetarian|vegan/.test(text);
  intent.avoidPork = /돼지고기.*(빼|제외|안)|no pork|without pork/.test(text);
  intent.avoidBeef = /소고기.*(빼|제외|안)|no beef|without beef/.test(text);
  intent.wantsSweet = /달달|달콤|단맛|sweet/.test(text);
  intent.avoidSour = /(?:신\s*거|신맛|시큼|새콤|상큼|sour).*(?:말고|빼|제외|싫|안)/.test(text);
  intent.caffeineFree = /카페인(?:이|은|는)?\s*(?:(?:완전히|전혀|아예)\s*)?(?:없는|없|0|제로)|무카페인|caffeine[- ]?free|zero caffeine/.test(text);
  intent.decaf = /디카페인|decaf/.test(text);
  intent.coffee = /커피|아메리카노|카페라떼|에스프레소|coffee|espresso/.test(text) || intent.decaf;
  if (/음료|drink|커피|디카페인|아메리카노|카페라떼|에스프레소/.test(text)) intent.category = "음료";
  else if (/국물|수프|찌개|(?<![설사])탕(?!수육)/.test(text) && !/국물\s*말고|국물\s*빼고/.test(text)) intent.category = "국물";
  else if (/밥|식사|점심|저녁|rice/.test(text)) intent.category = "식사";
  else if (/사이드|간식|side/.test(text)) intent.category = "사이드";
  else if (/디저트|후식|dessert/.test(text)) intent.category = "디저트";
  if (
    intent.action === "add" ||
    intent.action === "remove" ||
    intent.action === "ask"
  ) {
    const cleaned = text
      .replace(
        /(담아줘|담아|추가해줘|추가|넣어줘|넣어|빼줘|빼고|삭제해줘|삭제|제거해줘|제거|있어\?|얼마야\?|가격|add|remove)/g,
        "",
      )
      .replace(/(\d+|한|두|세|네|하나|둘|셋|넷)\s*(개|잔|그릇)/g, "")
      .trim();
    intent.menuName = cleaned || undefined;
  }
  return intent;
}

/** A request for a past completed order, separate from the latest unpurchased suggestion. */
export function asksForPreviousOrder(input: string): boolean {
  const text = input.trim().toLocaleLowerCase();
  return /(?:이전에|전에|지난번|예전에|지난\s*주문).*(?:주문|먹었|시켰)|(?:주문|시켰|먹었).*(?:했던|했었|한\s*메뉴)/.test(text);
}

/** A short add command refers to the last complete proposal, not to a new dish name. */
export function addsCurrentRecommendation(input: string): boolean {
  const compact = input.trim().toLowerCase().replace(/[,.!?。]/g, "").replace(/\s+/g, "");
  return /^(?:(?:좋아|그래|응|네|그럼|오케이))?(?:추천한(?:거|것|메뉴))?(?:전부|모두|다)?(?:담아(?:줘|주세요)?|넣어(?:줘|주세요)?|추가해(?:줘|주세요)?)$/.test(compact);
}
