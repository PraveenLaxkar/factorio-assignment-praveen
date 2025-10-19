#!/usr/bin/env python3
import sys, json
from collections import deque, defaultdict
import math

def read_input():
    return json.load(sys.stdin)

class FlowNetwork:
    def __init__(self):
        self.adj = defaultdict(list)
        self.cap = {}

    def add_edge(self,u,v,c):
        if c<0: return
        if (u,v) not in self.cap:
            self.adj[u].append(v)
            self.adj[v].append(u)
            self.cap[(u,v)] = 0
            self.cap[(v,u)] = 0
        self.cap[(u,v)] += c

    def bfs(self,s,t,parent):
        parent.clear()
        q=deque([s]); parent[s]=None
        while q:
            u=q.popleft()
            for v in sorted(self.adj[u]): 
                if v not in parent and self.cap[(u,v)]>1e-12:
                    parent[v]=u
                    if v==t: return True
                    q.append(v)
        return False

    def max_flow(self,s,t):
        flow=0.0; parent={}
        while self.bfs(s,t,parent):
            path_flow=math.inf; v=t
            while v!=s:
                u=parent[v]
                path_flow=min(path_flow,self.cap[(u,v)])
                v=u
            v=t
            while v!=s:
                u=parent[v]
                self.cap[(u,v)]-=path_flow
                self.cap[(v,u)]+=path_flow
                v=u
            flow+=path_flow
        return flow,parent

def main():
    data=read_input()
    edges=data.get("edges",[])
    sources=data.get("sources",{})
    sink=data.get("sink")
    node_caps={n:d.get("cap") for n,d in data.get("nodes",{}).items() if "cap" in d}

    split_in={}  
    for n,cap in node_caps.items():
        split_in[n]=f"{n}_in"
    
    def map_in(n): return split_in.get(n,n)
    def map_out(n): return f"{n}_out" if n in split_in else n

    all_edges=[]
    for e in edges:
        u,v=e["from"],e["to"]
        lo=e.get("lo",0.0); hi=e.get("hi",0.0)
        all_edges.append((u,v,lo,hi))
    for n,cap in node_caps.items():
        all_edges.append((f"{n}_in",f"{n}_out",0.0,float(cap)))

    imbalance=defaultdict(float)
    G=FlowNetwork()
    for (u,v,lo,hi) in all_edges:
        cap=max(hi-lo,0.0)
        G.add_edge(map_out(u),map_in(v),cap)
        imbalance[map_out(u)]-=lo
        imbalance[map_in(v)]+=lo

    s_star,t_star="__super_s__","__super_t__"
    for node,b in imbalance.items():
        if abs(b)<1e-9: continue
        if b>0: 
            G.add_edge(s_star,node,b)
        else:
            G.add_edge(node,t_star,-b)
    
    flow1,_=G.max_flow(s_star,t_star)
    total_demand=sum(max(b,0) for b in imbalance.values())
    
    if flow1+1e-9<total_demand:
        reachable=set()
        def dfs(u):
            if u in reachable: return
            reachable.add(u)
            for v in sorted(G.adj[u]):
                if G.cap[(u,v)]>1e-9 and v not in reachable:
                    dfs(v)
        dfs(s_star)
        cut_nodes=[n for n in sorted(reachable) if not n.startswith("__")]
        deficit=total_demand-flow1
        print(json.dumps({
            "status":"infeasible",
            "cut_reachable":cut_nodes,
            "deficit":{"demand_balance":deficit}
        }))
        return

    H=FlowNetwork()
    for (u,v,lo,hi) in all_edges:
        cap=max(hi-lo,0.0)
        H.add_edge(map_out(u),map_in(v),cap)
    
    s_sup="__S__"; t_sup=map_in(sink)
    for s,v in sources.items():
        H.add_edge(s_sup,map_in(s),v)
    
    total_supply=sum(sources.values())
    maxflow,_=H.max_flow(s_sup,t_sup)

    if maxflow+1e-9<total_supply:
        print(json.dumps({
            "status":"infeasible",
            "cut_reachable":["some sources"],
            "deficit":{"demand_balance":total_supply-maxflow}
        }))
        return

    flows=[]
    for (u,v,lo,hi) in all_edges:
        if u.startswith("__") or v.startswith("__"): continue
        f_used = H.cap.get((map_in(v), map_out(u)), 0.0) 
        actual=lo+f_used
        if actual>1e-9:
            flows.append({"from":u,"to":v,"flow":actual})

    print(json.dumps({
        "status":"ok",
        "max_flow_per_min":total_supply,
        "flows":flows
    }))

if __name__=="__main__":
    main()