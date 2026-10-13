"use client"

import * as React from "react"
import { cn } from "cn"

/* 데이터 표(옛 .tablewrap + table.tbl). 바깥 상자가 가로 스크롤 컨테이너이자 테두리라서 containerClassName 으로 높이 제한 등을 준다.
   머리 행은 그 컨테이너 안에서 sticky 다(컨테이너를 둘로 겹치면 sticky 기준이 바뀌므로 겹치지 않는다).
   containerProps 는 데이터 그리드가 그 컨테이너를 세로 스크롤 상자(가상 스크롤 기준)로 쓸 때 ref·style 을 건넨다. */
function Table({ className, containerClassName, containerProps, ...props }: React.ComponentProps<"table"> & { containerClassName?: string; containerProps?: React.ComponentProps<"div"> }) {
  return (
    <div data-slot="table-container" {...containerProps} className={cn("mt-2 overflow-x-auto rounded-[10px] border border-border", containerClassName)}>
      <table
        data-slot="table"
        className={cn("w-full border-collapse text-[16px] leading-[1.6] tabular-nums [&_a]:text-foreground [&_a]:no-underline [&_a:hover]:underline", className)}
        {...props}
      />
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return <thead data-slot="table-header" className={className} {...props} />
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return <tbody data-slot="table-body" className={cn("[&_tr:last-child_td]:border-b-0", className)} {...props} />
}

function TableRow({ className, total, ...props }: React.ComponentProps<"tr"> & { total?: boolean }) {
  return <tr data-slot="table-row" className={cn("hover:bg-pn2", total && "[&_td]:bg-muted [&_td]:font-bold", className)} {...props} />
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn("sticky top-0 border-b border-border bg-muted px-2.5 py-2.5 text-right text-[14px] font-bold whitespace-nowrap text-muted-foreground first:text-left", className)}
      {...props}
    />
  )
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return <td data-slot="table-cell" className={cn("border-b border-border px-2.5 py-2.5 text-right whitespace-nowrap first:text-left", className)} {...props} />
}

export { Table, TableHeader, TableBody, TableHead, TableRow, TableCell }
