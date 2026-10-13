import * as React from "react"
import { cn } from "cn"

/* 안내 상자(옛 .box): 점선 테두리. 위험 알림이 아니라 정보 안내라서 role="note" 로 둔다(shadcn 기본 role="alert" 는 스크린리더가 끼어들어 읽는다). */
function Alert({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="alert"
      role="note"
      className={cn("mt-[18px] rounded-[12px] border border-dashed border-line2 bg-muted px-[18px] py-4 text-[14px] text-muted-foreground [&_b]:text-foreground", className)}
      {...props}
    />
  )
}

export { Alert }
