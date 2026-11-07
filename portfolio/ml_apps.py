"""Small, reproducible ML baselines implemented with the Python standard library."""
import math
import random
import re
import statistics
from collections import Counter
from .data_apps import parse
from .validation import ValidationError, integer

def number(value, name, low, high):
    if isinstance(value, bool):
        raise ValidationError(f'{name} must be numeric')
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValidationError(f'{name} must be numeric') from None
    if not math.isfinite(result) or not low <= result <= high:
        raise ValidationError(f'{name} must be finite and between {low} and {high}')
    return result

def auc(labels, scores):
    positives = sum(labels)
    negatives = len(labels)-positives
    if not positives or not negatives:
        return None
    pairs = sorted(zip(scores,labels))
    rank_sum, start = 0, 0
    while start < len(pairs):
        end = start+1
        while end < len(pairs) and pairs[end][0] == pairs[start][0]:
            end += 1
        rank_sum += sum(y for _,y in pairs[start:end]) * (start+1+end)/2
        start = end
    return (rank_sum-positives*(positives+1)/2)/(positives*negatives)

def metrics(labels, scores, threshold=.5):
    tp=fp=tn=fn=0
    for y,p in zip(labels,scores):
        predicted=p>=threshold
        tp += y==1 and predicted
        fp += y==0 and predicted
        tn += y==0 and not predicted
        fn += y==1 and not predicted
    precision=tp/(tp+fp) if tp+fp else None
    recall=tp/(tp+fn) if tp+fn else None
    return {'accuracy':(tp+tn)/len(labels),'precision':precision,'recall':recall,
            'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
            'confusion':{'tp':tp,'fp':fp,'tn':tn,'fn':fn},'roc_auc':auc(labels,scores),
            'brier':statistics.mean((p-y)**2 for y,p in zip(labels,scores)),
            'log_loss':-statistics.mean(y*math.log(max(1e-15,p))+(1-y)*math.log(max(1e-15,1-p)) for y,p in zip(labels,scores))}

def evaluate(data):
    headers,rows=parse(data)
    if 'actual' not in headers or 'score' not in headers:
        raise ValidationError('CSV requires actual and score columns')
    labels,scores=[],[]
    for index,row in enumerate(rows,2):
        y=number(row[headers.index('actual')],f'actual at record {index}',0,1)
        if y not in (0,1):
            raise ValidationError('actual labels must be 0 or 1')
        labels.append(int(y))
        scores.append(number(row[headers.index('score')],f'score at record {index}',0,1))
    threshold=number(data.get('threshold',.5),'threshold',0,1)
    bins=[]
    for index in range(5):
        selected=[i for i,p in enumerate(scores) if min(4,int(p*5))==index]
        bins.append({'range':f'{index/5:.1f}–{(index+1)/5:.1f}', 'count':len(selected),
                     'mean_score':statistics.mean(scores[i] for i in selected) if selected else None,
                     'observed_rate':statistics.mean(labels[i] for i in selected) if selected else None})
    return {'rows':len(rows),'threshold':threshold,'positive_rate':sum(labels)/len(labels),
            'metrics':metrics(labels,scores,threshold),'calibration':bins,
            'predictions':[{'record':index,'actual':actual,'score':score,'predicted':int(score>=threshold)}
                           for index,(actual,score) in enumerate(zip(labels,scores),2)],
            'thresholds':[{'threshold':i/10,**metrics(labels,scores,i/10)} for i in range(11)]}

def sigmoid(value):
    if value>=0:
        return 1/(1+math.exp(-value))
    exponent=math.exp(value)
    return exponent/(1+exponent)

def train(data):
    headers,rows=parse(data)
    target=data.get('target','label')
    if target not in headers:
        raise ValidationError('Select an existing target column')
    features=[h for h in headers if h!=target]
    if not 1 <= len(features) <= 12 or not 8 <= len(rows) <= 1000:
        raise ValidationError('Training requires 8–1,000 rows and 1–12 numeric feature columns')
    seed=integer(data,'seed',0,1_000_000) if 'seed' in data else 42
    x,y=[],[]
    for index,row in enumerate(rows,2):
        label=number(row[headers.index(target)],f'label at record {index}',0,1)
        if label not in (0,1):
            raise ValidationError('Target labels must be 0 or 1')
        y.append(int(label))
        x.append([number(row[headers.index(h)],f'{h} at record {index}',-1e9,1e9) for h in features])
    if min(y.count(0),y.count(1)) < 4:
        raise ValidationError('Include at least four examples of each class')
    # Identical feature vectors across a random split would overstate generalization.
    if len(set(map(tuple,x))) != len(x):
        raise ValidationError('Duplicate feature rows found. Deduplicate or use an appropriate grouped split first')
    rng=random.Random(seed)
    train_ids,test_ids=[],[]
    for label in (0,1):
        ids=[i for i,value in enumerate(y) if value==label]
        rng.shuffle(ids)
        count=max(1,round(len(ids)*.25))
        test_ids.extend(ids[:count]); train_ids.extend(ids[count:])
    means=[statistics.mean(x[i][j] for i in train_ids) for j in range(len(features))]
    scales=[max(statistics.pstdev(x[i][j] for i in train_ids) or 1,1e-12) for j in range(len(features))]
    scaled=[[1,*[(row[j]-means[j])/scales[j] for j in range(len(features))]] for row in x]
    weights=[0.]*(len(features)+1)
    losses=[]
    for epoch in range(201):
        predictions=[sigmoid(sum(w*v for w,v in zip(weights,scaled[i]))) for i in train_ids]
        if epoch%20==0:
            losses.append({'epoch':epoch,'log_loss':metrics([y[i] for i in train_ids],predictions)['log_loss']})
        if epoch==200:
            break
        gradient=[0.]*len(weights)
        for i,p in zip(train_ids,predictions):
            for j,value in enumerate(scaled[i]):
                gradient[j] += (p-y[i])*value
        weights=[w-.1*(gradient[j]/len(train_ids)+(.01*w if j else 0)) for j,w in enumerate(weights)]
    predictions=[sigmoid(sum(w*v for w,v in zip(weights,scaled[i]))) for i in test_ids]
    majority=int(sum(y[i] for i in train_ids)>len(train_ids)/2)
    return {'train_rows':len(train_ids),'test_rows':len(test_ids),'seed':seed,
            'metrics':metrics([y[i] for i in test_ids],predictions),
            'baseline_accuracy':sum(y[i]==majority for i in test_ids)/len(test_ids),
            'loss_history':losses,'features':[{'name':name,'weight':weights[j+1],'mean':means[j],'scale':scales[j]} for j,name in enumerate(features)],
            'model':{'algorithm':'standardized binary logistic regression','intercept':weights[0],
                     'weights':weights[1:],'features':features,'means':means,'scales':scales,'threshold':.5},
            'predictions':[{'record':i+2,'actual':y[i],'score':p} for i,p in zip(test_ids,predictions)],
            'train_records':[i+2 for i in train_ids], 'test_records':[i+2 for i in test_ids]}

STOPWORDS=set('a an and are as at be by for from in is it of on or that the this to was with'.split())

def tokens(text):
    return [word for word in re.findall(r'\b\w\w+\b',text.lower()) if word not in STOPWORDS]

def search(data):
    documents=data.get('documents')
    query=data.get('query')
    if not isinstance(documents,str) or len(documents.encode('utf-8'))>200_000:
        raise ValidationError('Documents must be text of at most 200 KB')
    if not isinstance(query,str) or not query.strip() or len(query)>500:
        raise ValidationError('Enter a query of 1–500 characters')
    docs=[doc.strip() for doc in re.split(r'\n\s*---\s*\n',documents) if doc.strip()]
    if not 2<=len(docs)<=100:
        raise ValidationError('Provide 2–100 documents separated by a line containing ---')
    algorithm=data.get('algorithm','tfidf')
    if algorithm not in ('tfidf','bm25'): raise ValidationError('algorithm must be tfidf or bm25')
    top_k=integer(data,'top_k',1,20) if 'top_k' in data else 10
    counts=[Counter(tokens(doc)) for doc in docs]
    df=Counter(term for count in counts for term in count)
    if not df:
        raise ValidationError('Documents contain no searchable terms')
    idf={term:math.log((1+len(docs))/(1+freq))+1 for term,freq in df.items()}
    def vector(count):
        raw={term:(1+math.log(freq))*idf[term] for term,freq in count.items() if term in idf}
        norm=math.sqrt(sum(v*v for v in raw.values())) or 1
        return {term:v/norm for term,v in raw.items()}
    q=vector(Counter(tokens(query)))
    results=[]
    average_length=sum(sum(c.values()) for c in counts)/len(docs) or 1
    for index,count in enumerate(counts):
        vec=vector(count)
        contributions=sorted(((term,qv*vec.get(term,0)) for term,qv in q.items() if term in vec),key=lambda x:-x[1])
        score=sum(value for _,value in contributions)
        if score>0:
            bm25=sum(math.log(1+(len(docs)-df[term]+.5)/(df[term]+.5))*(count[term]*2.5)/(count[term]+1.5*(.25+.75*sum(count.values())/average_length)) for term in q if count[term])
            results.append({'document':index+1,'score':bm25 if algorithm=='bm25' else min(1.,score),'tfidf_score':min(1.,score),'bm25_score':bm25,'excerpt':docs[index][:600],
                            'matched_terms':[{'term':term,'contribution':value} for term,value in contributions]})
    results.sort(key=lambda r:(-r['score'],r['document']))
    return {'documents':len(docs),'vocabulary':len(idf),'query_terms':list(q),
            'unseen_terms':sorted(set(tokens(query))-set(idf)), 'results':results[:top_k], 'algorithm':algorithm, 'top_k':top_k,
            'capabilities':{'tables':[{'title':'Ranking comparison','headers':['Document','TF-IDF cosine','BM25 score'],'rows':[[r['document'],round(r['tfidf_score'],5),round(r['bm25_score'],5)] for r in results[:top_k]]}], 'notes':['BM25 uses k1=1.5, b=0.75 and unique query terms. Scores are unbounded ranking values, not probabilities. Matched-term contributions still describe TF-IDF.']},
            'method':('BM25 lexical ranking' if algorithm=='bm25' else 'TF-IDF cosine similarity (lexical baseline, not neural semantic embeddings)')}
