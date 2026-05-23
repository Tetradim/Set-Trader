import { strict as assert } from 'node:assert';
import {
  buildTickerChartData,
  computeResizeState,
  getChartDomain,
} from './ticker-card-utils';

const history = [
  { time: 1000, price: 100 },
  { time: 2000, price: 104 },
  { time: 3000, price: 102 },
];

{
  const data = buildTickerChartData(history, 105);
  assert.equal(data.length, 3);
  assert.deepEqual(data.map((point) => point.price), [100, 104, 102]);
}

{
  const data = buildTickerChartData([{ time: 1000, price: 101 }], 103);
  assert.equal(data.length, 2);
  assert.equal(data[0].price, 101);
  assert.equal(data[1].price, 103);
  assert.ok(data[1].time > data[0].time);
}

{
  const data = buildTickerChartData([], 88);
  assert.equal(data.length, 2);
  assert.equal(data[0].price, 88);
  assert.equal(data[1].price, 88);
}

{
  const domain = getChartDomain(history);
  assert.deepEqual(domain, [99.6, 104.4]);
}

{
  const state = computeResizeState({
    direction: 'se',
    startWidth: 220,
    startHeight: 240,
    deltaX: 31,
    deltaY: 19,
    minWidth: 200,
    minHeight: 215,
    snap: false,
    snapGrid: 10,
  });
  assert.deepEqual(state, { width: 251, height: 259 });
}

{
  const state = computeResizeState({
    direction: 'nw',
    startWidth: 260,
    startHeight: 260,
    deltaX: 90,
    deltaY: 90,
    minWidth: 200,
    minHeight: 215,
    snap: false,
    snapGrid: 10,
  });
  assert.deepEqual(state, { width: 200, height: 215 });
}

{
  const state = computeResizeState({
    direction: 'e',
    startWidth: 223,
    startHeight: 241,
    deltaX: 14,
    deltaY: 99,
    minWidth: 200,
    minHeight: 215,
    snap: true,
    snapGrid: 10,
  });
  assert.deepEqual(state, { width: 240, height: 241 });
}
