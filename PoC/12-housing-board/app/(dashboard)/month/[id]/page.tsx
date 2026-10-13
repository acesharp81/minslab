import { notFound } from 'next/navigation';

/* 정책별 월 실적 자료가 없어 과거 전국 월별 화면은 공개하지 않는다. */
export default function LegacyMonthPage() { notFound(); }
