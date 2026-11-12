/** Pure helpers for the CPM Gantt view (RP-10), kept out of the component file. */

/** Bar position as percentages of the makespan (day 0 at the left edge). */
export function estiloBarra(
  inicioTemprano: number,
  duracionDias: number,
  makespan: number,
): { left: string; width: string } {
  if (makespan <= 0) return { left: '0%', width: '0%' }
  return {
    left: `${((inicioTemprano / makespan) * 100).toFixed(2)}%`,
    width: `${((duracionDias / makespan) * 100).toFixed(2)}%`,
  }
}
