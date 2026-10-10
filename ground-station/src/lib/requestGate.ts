// This gate serializes requests and spaces their start times, including failures.
export function createRequestGate(
  intervalMs: number,
  clock = () => performance.now(),
  wait = (milliseconds: number) =>
    new Promise<void>((resolve) => setTimeout(resolve, milliseconds)),
) {
  let lastStarted = -Infinity;
  let queue: Promise<unknown> = Promise.resolve();
  return function run<T>(task: () => Promise<T>): Promise<T> {
    const result = queue.then(async () => {
      while (clock() - lastStarted < intervalMs) {
        await wait(intervalMs - (clock() - lastStarted));
      }
      lastStarted = clock();
      return task();
    });
    queue = result.catch(() => {});
    return result;
  };
}
