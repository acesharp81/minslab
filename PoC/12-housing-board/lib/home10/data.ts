/* PoC 10 HOME의 읽기 전용 변환본. 원본 식별자·결측·검토 상태를 유지한다. */
import converted from '../../data/home10/converted.json';

export type HomeProject = (typeof converted.projects)[number];
export const home10 = converted;
