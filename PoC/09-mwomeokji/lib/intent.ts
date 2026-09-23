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

export function parseIntent(input: string): OrderIntent {
  const text = input.trim().toLowerCase();
  const intent: OrderIntent = { action: "recommend" };
  if (/직원|사장님.*불러|help|staff/.test(text)) intent.action = "help";
  else if (/빼줘|빼고|삭제|제거|remove/.test(text)) intent.action = "remove";
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
  if (/절대.*(안|못).*맵|매운.*절대|매운.*못|not spicy|no spice/.test(text))
    intent.maxSpiceLevel = 0;
  else if (/안 맵|덜 맵|순한|mild/.test(text)) intent.maxSpiceLevel = 1;
  intent.wantsWarm = /따뜻|뜨끈|국물|warm|hot/.test(text);
  intent.wantsCool = /시원|차가운|cold|cool/.test(text);
  intent.wantsMild = /안 맵|덜 맵|순한|mild|not spicy/.test(text);
  intent.vegetarian = /채식|비건|vegetarian|vegan/.test(text);
  intent.avoidPork = /돼지고기.*(빼|제외|안)|no pork|without pork/.test(text);
  intent.avoidBeef = /소고기.*(빼|제외|안)|no beef|without beef/.test(text);
  if (/음료|drink|커피/.test(text)) intent.category = "음료";
  else if (/밥|식사|rice/.test(text)) intent.category = "식사";
  else if (/사이드|간식|side/.test(text)) intent.category = "사이드";
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
