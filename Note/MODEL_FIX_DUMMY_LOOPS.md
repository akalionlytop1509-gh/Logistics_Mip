# Huong sua mo hinh de xu ly Dummy Loops

## 1. Van de hien tai

Mo hinh hien tai dang dung single-commodity flow:

```text
inflow + supply = outflow + demand
```

Dieu nay lam solver khong phan biet hang import, export hay domestic. Neu mot node vua co the nhan hang vua co the phat hang, vi du Port hoac KCN, solver co the tao dong chay vong nhu:

```text
Port -> ICD -> KCN -> Port
```

Dong chay nay khong phuc vu them nhu cau that, nhung van duoc tinh vao tong flow tren mang.

## 2. Nguyen nhan chinh cua viec "lach luat"

Rang buoc hien tai:

```text
road_flow <= k_road * total_network_flow
```

Trong do:

```text
total_network_flow = sum tat ca flow tren cac arc
```

Neu solver tao them mot dummy loop bang rail/barge/sea, `total_network_flow` tang len. Khi mau so tang, solver duoc phep dung them road flow. Neu road route re hon phan chi phi dummy loop, solver se chon dummy loop vi do la nghiem toi uu ve chi phi.

Day la loi formulation, khong phai loi cua solver.

## 3. Vi sao DAG khong phai cach sua toi uu

Da thu cac huong:

- Cam cycle tren tat ca node: de gay infeasible vi flow import va export co the can di nguoc huong nhau.
- Loai Port khoi DAG: solver co the tao loop qua Port.
- Chi cho phep cycle qua ICD/KCN: solver co the doi sang loop qua node duoc ngoai le.

DAG chi cam mot so hinh dang vong lap. Neu mo hinh van cho dummy loop tao loi ich trong `k_road`, solver se tim duong khac de khai thac.

## 4. Huong sua khuyen nghi

Nen tach flow thanh nhieu commodity theo muc dich logistics:

```text
x_import[u, v, m]
x_export[u, v, m]
x_domestic[u, v, m]  # neu data co luong noi dia rieng
```

Y nghia:

- `import`: Port phat hang, KCN/DC noi dia nhan hang.
- `export`: KCN/nha may phat hang, Port nhan hang.
- `domestic`: KCN/nha may phat hang, DC noi dia nhan hang.

KCN van co the la supply node binh thuong. Diem khac la supply cua KCN duoc gan vao commodity dung muc dich, vi du export hoac domestic, thay vi tron chung voi import.

## 5. Sua rang buoc k_road

Khong nen dung tong arc flow lam mau so:

```text
road_flow <= k_road * total_network_flow
```

Nen dung nhu cau that, la mot gia tri co dinh hoac khong the bi dummy loop lam tang:

```text
road_flow <= k_road * real_required_flow
```

Trong do:

```text
real_required_flow = import_demand + export_demand + domestic_demand
```

Neu can chat hon, ap dung rieng cho tung commodity:

```text
road_import  <= k_road * import_demand
road_export  <= k_road * export_demand
road_domestic <= k_road * domestic_demand
```

## 6. Rang buoc capacity sau khi tach commodity

Capacity cua moi arc van la capacity vat ly dung chung:

```text
sum_k x[k, u, v, m] <= capacity[u, v, m] * y[u, v, m]
```

Nghia la import, export va domestic cung tranh capacity tren cung mot tuyen.

## 7. Ket luan

Cach sua tot nhat la:

1. Tach flow thanh import/export/domestic commodity.
2. Doi mau so cua `k_road` tu `total_network_flow` sang nhu cau that.
3. Giu capacity tren arc la tong flow cua tat ca commodity.
4. Bo dan cac rang buoc DAG/cycle mang tinh va loi, vi chung chi xu ly trieu chung.

Ket qua mong muon: dummy loop khong con lam tang quota road, nen no chi tao them chi phi va se bi solver tu loai bo.
